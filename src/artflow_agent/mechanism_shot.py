from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MechanismShotFrame(StrictContract):
    label: Literal["closed_start", "open", "closed_end"]
    frame: int = Field(ge=1, le=48)


class MechanismShotRequest(StrictContract):
    schema_id: Literal["artflow-mechanism-shot-request/1"] = (
        "artflow-mechanism-shot-request/1"
    )
    request_id: str = Field(pattern=r"^mechanism-shot-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    capability_id: Literal["unreal.sequencer.mechanism_shot.v1"]
    mechanism_request_sha256: str = Field(pattern=SHA256_PATTERN)
    mechanism_unreal_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    skeletal_mesh_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    skeletal_mesh_sha256: str = Field(pattern=SHA256_PATTERN)
    skeleton_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    skeleton_sha256: str = Field(pattern=SHA256_PATTERN)
    animation_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    animation_sha256: str = Field(pattern=SHA256_PATTERN)
    display_rate_fps: Literal[24]
    playback_start_frame: Literal[1]
    playback_end_frame: Literal[49]
    frames: list[MechanismShotFrame] = Field(min_length=3, max_length=3)
    camera_location_cm: tuple[float, float, float]
    camera_target_cm: tuple[float, float, float]
    camera_focal_length_mm: float = Field(ge=24, le=85)
    camera_binding_mode: Literal["spawnable"]
    camera_cut_binding_space: Literal["sequence_local"]
    camera_transform_track: Literal["constant"]
    cue_light_intensity: float = Field(ge=500, le=5000)
    cue_light_temperature_kelvin: float = Field(ge=2500, le=8000)
    candidate_scene_path: str = Field(
        pattern=r"^/Game/ArtFlow/Sessions/AF_[a-f0-9]{12}/Candidates/MechanismShot_B_[a-f0-9]{12}$"
    )
    sequence_asset_path: str = Field(
        pattern=r"^/Game/ArtFlow/Sequences/Generated/LS_AF_MechanismShot_[a-f0-9]{12}\.LS_AF_MechanismShot_[a-f0-9]{12}$"
    )
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> MechanismShotRequest:
        if [(item.label, item.frame) for item in self.frames] != [
            ("closed_start", 1),
            ("open", 24),
            ("closed_end", 48),
        ]:
            raise ValueError("mechanism shot uses the registered 1, 24 and 48 frames")
        if canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"})) != (
            self.request_sha256
        ):
            raise ValueError("mechanism shot request fingerprint mismatch")
        return self


def _asset_file(root: Path, object_path: str) -> Path:
    package = object_path.split(".", 1)[0].removeprefix("/Game/")
    return root / "integrations/unreal/ArtFlowBridgeHost/Content" / f"{package}.uasset"


def compile_mechanism_shot_request(*, root: Path) -> MechanismShotRequest:
    root = root.resolve()
    mechanism_root = root / "artifacts/goal/m51-s1-mechanism-rig"
    mechanism_request = json.loads(
        (mechanism_root / "mechanism-rig-request.json").read_text(encoding="utf-8")
    )
    unreal_receipt = json.loads(
        (mechanism_root / "unreal-mechanism-rig-receipt.json").read_text(encoding="utf-8")
    )
    if unreal_receipt["request_sha256"] != mechanism_request["request_sha256"]:
        raise ValueError("mechanism Unreal receipt references another request")
    content = root / "integrations/unreal/ArtFlowBridgeHost/Content"
    source = content / (
        unreal_receipt["candidate_scene_path"].removeprefix("/Game/") + ".umap"
    )
    asset_paths = {
        "skeletal_mesh": unreal_receipt["skeletal_mesh_path"],
        "skeleton": unreal_receipt["skeleton_path"],
        "animation": unreal_receipt["animation_path"],
    }
    asset_files = {name: _asset_file(root, path) for name, path in asset_paths.items()}
    if not source.is_file() or not all(path.is_file() for path in asset_files.values()):
        raise FileNotFoundError("mechanism shot source asset is unavailable")
    core = {
        "schema_id": "artflow-mechanism-shot-request/1",
        "session_id": mechanism_request["session_id"],
        "capability_id": "unreal.sequencer.mechanism_shot.v1",
        "mechanism_request_sha256": mechanism_request["request_sha256"],
        "mechanism_unreal_receipt_sha256": unreal_receipt["receipt_sha256"],
        "source_candidate_scene_path": unreal_receipt["candidate_scene_path"],
        "source_candidate_sha256": file_sha256(source),
        "skeletal_mesh_path": asset_paths["skeletal_mesh"],
        "skeletal_mesh_sha256": file_sha256(asset_files["skeletal_mesh"]),
        "skeleton_path": asset_paths["skeleton"],
        "skeleton_sha256": file_sha256(asset_files["skeleton"]),
        "animation_path": asset_paths["animation"],
        "animation_sha256": file_sha256(asset_files["animation"]),
        "display_rate_fps": 24,
        "playback_start_frame": 1,
        "playback_end_frame": 49,
        "frames": [
            {"label": "closed_start", "frame": 1},
            {"label": "open", "frame": 24},
            {"label": "closed_end", "frame": 48},
        ],
        "camera_location_cm": [2500.0, -1050.0, 320.0],
        "camera_target_cm": [2500.0, 0.0, 190.0],
        "camera_focal_length_mm": 42.0,
        "camera_binding_mode": "spawnable",
        "camera_cut_binding_space": "sequence_local",
        "camera_transform_track": "constant",
        "cue_light_intensity": 1800.0,
        "cue_light_temperature_kelvin": 4200.0,
    }
    identity = canonical_sha256(core)[:12]
    core["candidate_scene_path"] = (
        f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/MechanismShot_B_{identity}"
    )
    core["sequence_asset_path"] = (
        f"/Game/ArtFlow/Sequences/Generated/LS_AF_MechanismShot_{identity}."
        f"LS_AF_MechanismShot_{identity}"
    )
    provisional = canonical_sha256(core)
    core["request_id"] = f"mechanism-shot-{provisional[:16]}"
    core["request_sha256"] = canonical_sha256(core)
    return MechanismShotRequest.model_validate(core)
