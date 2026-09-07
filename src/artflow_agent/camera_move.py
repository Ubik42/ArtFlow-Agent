from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


class CameraMovePose(StrictContract):
    label: Literal["start", "middle", "end"]
    frame: int = Field(ge=0, le=120)
    location_cm: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]


class CameraMoveRequest(StrictContract):
    schema_id: Literal["artflow-camera-move-request/1"] = "artflow-camera-move-request/1"
    request_id: str = Field(pattern=r"^camera-move-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    capability_id: Literal["blender.camera_move.three_key_dolly.v1"]
    shot_package_request_sha256: str = Field(pattern=SHA256_PATTERN)
    unreal_shot_package_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    blender_shot_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    source_sequence_path: str
    source_sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    display_rate_fps: int = Field(ge=12, le=60)
    playback_start_frame: int = Field(ge=0)
    playback_end_frame: int = Field(gt=0, le=2400)
    poses: list[CameraMovePose] = Field(min_length=3, max_length=3)
    output_stem: Literal["AF_ShrineCourtyard_CameraMove"]
    sequence_asset_path: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_request(self) -> CameraMoveRequest:
        if [pose.label for pose in self.poses] != ["start", "middle", "end"]:
            raise ValueError("camera move poses must be start, middle and end")
        if [pose.frame for pose in self.poses] != [0, 60, 119]:
            raise ValueError("camera move uses the registered 0, 60 and 119 frame keys")
        if not all(
            self.playback_start_frame <= pose.frame < self.playback_end_frame for pose in self.poses
        ):
            raise ValueError("camera move key lies outside the playback range")
        if canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"})) != (
            self.request_sha256
        ):
            raise ValueError("camera move request fingerprint mismatch")
        return self


class CameraMoveArtifact(StrictContract):
    kind: Literal["blend", "preview_start", "preview_middle", "preview_end"]
    relative_path: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class BlenderCameraMoveReceipt(StrictContract):
    schema_id: Literal["artflow-blender-camera-move-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.camera_move.three_key_dolly.v1"]
    blender_version: str
    status: Literal["succeeded"]
    camera_label: Literal["ArtFlow_Shot_Camera"]
    keyframe_count: Literal[3]
    frame_numbers: list[int] = Field(min_length=3, max_length=3)
    translation_distance_cm: float = Field(gt=0, le=1000)
    artifacts: list[CameraMoveArtifact] = Field(min_length=4, max_length=4)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderCameraMoveReceipt:
        if self.frame_numbers != [0, 60, 119]:
            raise ValueError("Blender camera move returned unexpected frames")
        if {artifact.kind for artifact in self.artifacts} != {
            "blend",
            "preview_start",
            "preview_middle",
            "preview_end",
        }:
            raise ValueError("Blender camera move receipt has incomplete artifacts")
        expected = canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"}))
        if expected != self.receipt_sha256:
            raise ValueError("Blender camera move receipt fingerprint mismatch")
        return self


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rotation_toward(
    location: tuple[float, float, float], target: tuple[float, float, float]
) -> tuple[float, float, float]:
    dx, dy, dz = (target[index] - location[index] for index in range(3))
    horizontal = math.hypot(dx, dy)
    return (
        round(math.degrees(math.atan2(dz, horizontal)), 4),
        round(math.degrees(math.atan2(dy, dx)), 4),
        0.0,
    )


def compile_camera_move_request(*, project_root: Path) -> CameraMoveRequest:
    shot_root = project_root / "artifacts/goal/m23-s5-camera-light"
    package_root = project_root / "artifacts/goal/m36-s1-shot-package"
    shot_package = json.loads((package_root / "shot-package-request.json").read_text("utf-8"))
    unreal_receipt = json.loads(
        (package_root / "unreal-shot-package-receipt.json").read_text("utf-8")
    )
    blender_receipt = json.loads((shot_root / "shot-receipt.json").read_text("utf-8"))
    if unreal_receipt["request_sha256"] != shot_package["request_sha256"]:
        raise ValueError("Unreal shot package references another request")
    if blender_receipt["receipt_sha256"] != shot_package["blender_shot_receipt_sha256"]:
        raise ValueError("shot package references another Blender previs")
    source_blend = shot_root / "AF_ShrineCourtyard_Shot.blend"
    sequence_file = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / (shot_package["sequence_asset_path"].split(".", 1)[0].removeprefix("/Game/") + ".uasset")
    )
    candidate_file = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / (shot_package["candidate_scene_path"].removeprefix("/Game/") + ".umap")
    )
    if not source_blend.is_file() or not sequence_file.is_file() or not candidate_file.is_file():
        raise ValueError("camera move source artifact is unavailable")
    target = (250.0, 0.0, 140.0)
    locations = [(-900.0, -180.0, 450.0), (-820.0, 0.0, 400.0), (-720.0, 180.0, 360.0)]
    core = {
        "schema_id": "artflow-camera-move-request/1",
        "session_id": shot_package["session_id"],
        "capability_id": "blender.camera_move.three_key_dolly.v1",
        "shot_package_request_sha256": shot_package["request_sha256"],
        "unreal_shot_package_receipt_sha256": unreal_receipt["receipt_sha256"],
        "blender_shot_receipt_sha256": blender_receipt["receipt_sha256"],
        "source_blend_sha256": _file_sha256(source_blend),
        "source_sequence_path": shot_package["sequence_asset_path"],
        "source_sequence_sha256": _file_sha256(sequence_file),
        "source_candidate_scene_path": shot_package["candidate_scene_path"],
        "source_candidate_sha256": _file_sha256(candidate_file),
        "display_rate_fps": shot_package["display_rate_fps"],
        "playback_start_frame": shot_package["playback_start_frame"],
        "playback_end_frame": shot_package["playback_end_frame"],
        "poses": [
            {
                "label": label,
                "frame": frame,
                "location_cm": location,
                "rotation_deg": _rotation_toward(location, target),
            }
            for label, frame, location in zip(
                ("start", "middle", "end"), (0, 60, 119), locations, strict=True
            )
        ],
        "output_stem": "AF_ShrineCourtyard_CameraMove",
    }
    identity = canonical_sha256(core)[:12]
    core["sequence_asset_path"] = (
        f"/Game/ArtFlow/Sequences/Generated/LS_AF_CameraMove_{identity}.LS_AF_CameraMove_{identity}"
    )
    provisional = canonical_sha256(core)
    core["request_id"] = f"camera-move-{provisional[:16]}"
    core["request_sha256"] = canonical_sha256(core)
    return CameraMoveRequest.model_validate(core)


def execute_blender_camera_move(
    request: CameraMoveRequest,
    *,
    project_root: Path,
    output_dir: Path,
    blender_executable: Path,
    timeout_seconds: int = 180,
) -> BlenderCameraMoveReceipt:
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    if project_root not in output_dir.parents:
        raise ValueError("Blender camera-move output must stay inside the project")
    source_blend = project_root / "artifacts/goal/m23-s5-camera-light/AF_ShrineCourtyard_Shot.blend"
    script = project_root / "integrations/blender/author_camera_move.py"
    if not source_blend.is_file() or not script.is_file() or not blender_executable.is_file():
        raise FileNotFoundError("Blender camera-move runtime dependency is missing")
    if _file_sha256(source_blend) != request.source_blend_sha256:
        raise ValueError("Blender camera-move source identity mismatch")
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "camera-move-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    subprocess.run(
        [
            str(blender_executable),
            "--background",
            "--factory-startup",
            "--python",
            str(script),
            "--",
            str(request_path),
            str(output_dir),
            str(source_blend),
        ],
        check=True,
        cwd=project_root,
        timeout=timeout_seconds,
    )
    receipt = BlenderCameraMoveReceipt.model_validate_json(
        (output_dir / "blender-camera-move-receipt.json").read_text(encoding="utf-8")
    )
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("Blender camera-move receipt belongs to another request")
    for artifact in receipt.artifacts:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir not in path.parents or _file_sha256(path) != artifact.sha256:
            raise ValueError("Blender camera-move artifact identity mismatch")
    return receipt
