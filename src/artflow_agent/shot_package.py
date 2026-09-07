from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


class ShotCamera(StrictContract):
    label: Literal["ArtFlow_Sequence_Camera"] = "ArtFlow_Sequence_Camera"
    location_cm: tuple[float, float, float]
    rotation_deg: tuple[float, float, float]
    horizontal_fov_deg: float = Field(ge=20.0, le=100.0)
    aspect_ratio: float = Field(ge=1.0, le=3.0)


class ShotLight(StrictContract):
    role: Literal["key", "fill", "rim"]
    actor_label: str
    rotation_deg: tuple[float, float, float]
    intensity_lux: float = Field(ge=0.0, le=20.0)
    temperature_kelvin: float = Field(ge=1000.0, le=15000.0)
    cast_shadows: bool


class ShotPackageRequest(StrictContract):
    schema_id: Literal["artflow-shot-package-request/1"] = "artflow-shot-package-request/1"
    request_id: str = Field(pattern=r"^shot-package-[a-f0-9]{16}$")
    session_id: str
    capability_id: Literal["unreal.sequencer.procedural_environment_shot.v1"]
    source_candidate_scene_path: str
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    native_pcg_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    blender_shot_request_sha256: str = Field(pattern=SHA256_PATTERN)
    blender_shot_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    camera: ShotCamera
    light_rig: list[ShotLight] = Field(min_length=3, max_length=3)
    display_rate_fps: int = Field(ge=12, le=60)
    playback_start_frame: int = Field(ge=0)
    playback_end_frame: int = Field(gt=0, le=2400)
    preview_frame: int = Field(ge=0)
    sequence_asset_path: str
    candidate_scene_path: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> ShotPackageRequest:
        if not self.playback_start_frame <= self.preview_frame < self.playback_end_frame:
            raise ValueError("preview frame must be inside the playback range")
        if {item.role for item in self.light_rig} != {"key", "fill", "rim"}:
            raise ValueError("shot package requires key, fill and rim roles")
        expected = canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"}))
        if expected != self.request_sha256:
            raise ValueError("shot package request fingerprint mismatch")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_shot_package_request(
    *,
    project_root: Path,
    shot_request_path: Path,
    shot_receipt_path: Path,
    native_pcg_receipt_path: Path,
) -> ShotPackageRequest:
    shot_request = json.loads(shot_request_path.read_text(encoding="utf-8"))
    shot_receipt = json.loads(shot_receipt_path.read_text(encoding="utf-8"))
    pcg_receipt = json.loads(native_pcg_receipt_path.read_text(encoding="utf-8"))
    if shot_receipt["request_sha256"] != shot_request["request_sha256"]:
        raise ValueError("Blender shot receipt references another request")
    if pcg_receipt.get("status") != "reconciled":
        raise ValueError("native PCG candidate must be reconciled before shot packaging")
    candidate_package = pcg_receipt["candidate_scene_path"]
    candidate_file = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / (candidate_package.removeprefix("/Game/") + ".umap")
    )
    if not candidate_file.is_file():
        raise ValueError("registered native PCG candidate file is unavailable")
    camera = shot_request["camera"]
    labels = {"key": "ArtFlow_KeyLight", "fill": "DirectionalLight", "rim": "ArtFlow_DCC_RimLight"}
    core = {
        "schema_id": "artflow-shot-package-request/1",
        "session_id": shot_request["session_id"],
        "capability_id": "unreal.sequencer.procedural_environment_shot.v1",
        "source_candidate_scene_path": candidate_package,
        "source_candidate_sha256": file_sha256(candidate_file),
        "native_pcg_receipt_sha256": pcg_receipt["receipt_sha256"],
        "blender_shot_request_sha256": shot_request["request_sha256"],
        "blender_shot_receipt_sha256": shot_receipt["receipt_sha256"],
        "camera": {
            "label": "ArtFlow_Sequence_Camera",
            "location_cm": camera["location_cm"],
            "rotation_deg": camera["rotation_deg"],
            "horizontal_fov_deg": camera["horizontal_fov_deg"],
            "aspect_ratio": camera["aspect_ratio"],
        },
        "light_rig": [
            {**item, "actor_label": labels[item["role"]]} for item in shot_receipt["unreal_rig"]
        ],
        "display_rate_fps": 24,
        "playback_start_frame": 0,
        "playback_end_frame": 120,
        "preview_frame": 48,
    }
    identity = canonical_sha256(core)[:12]
    core["sequence_asset_path"] = (
        f"/Game/ArtFlow/Sequences/Generated/LS_AF_{identity}.LS_AF_{identity}"
    )
    core["candidate_scene_path"] = (
        f"/Game/ArtFlow/Sessions/AF_{shot_request['session_sha256'][:12]}/Candidates/"
        f"ShotPackage_B_{identity}"
    )
    provisional = canonical_sha256(core)
    core["request_id"] = f"shot-package-{provisional[:16]}"
    core["request_sha256"] = canonical_sha256(core)
    return ShotPackageRequest.model_validate(core)
