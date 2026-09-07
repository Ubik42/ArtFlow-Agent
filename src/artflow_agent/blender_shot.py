from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


class UnrealCameraFact(StrictContract):
    label: Literal["ArtFlow_Camera"]
    location_cm: list[float] = Field(min_length=3, max_length=3)
    rotation_deg: list[float] = Field(min_length=3, max_length=3)
    horizontal_fov_deg: float = Field(ge=20, le=120)
    aspect_ratio: float = Field(ge=1, le=3)


class UnrealDirectionalLightFact(StrictContract):
    label: Literal["ArtFlow_KeyLight", "DirectionalLight"]
    location_cm: list[float] = Field(min_length=3, max_length=3)
    rotation_deg: list[float] = Field(min_length=3, max_length=3)
    intensity_lux: float = Field(ge=0, le=30)
    temperature_kelvin: float = Field(ge=1000, le=15000)
    use_temperature: bool
    cast_shadows: bool


class ShotRigLight(StrictContract):
    role: Literal["key", "fill", "rim"]
    rotation_deg: list[float] = Field(min_length=3, max_length=3)
    intensity_lux: float = Field(ge=0.05, le=10)
    temperature_kelvin: float = Field(ge=2500, le=12000)
    cast_shadows: bool


class BlenderShotRequest(StrictContract):
    schema_id: Literal["artflow-blender-shot-request/1"] = "artflow-blender-shot-request/1"
    request_id: str = Field(pattern=r"^blender-shot-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    session_sha256: str = Field(pattern=SHA256_PATTERN)
    source_level_sha256: str = Field(pattern=SHA256_PATTERN)
    source_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    layout_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.shot.rain_breakthrough.v1"] = (
        "blender.shot.rain_breakthrough.v1"
    )
    preset: Literal["rain_breakthrough"] = "rain_breakthrough"
    camera: UnrealCameraFact
    subject_origin_cm: list[float] = Field(min_length=3, max_length=3)
    source_lights: list[UnrealDirectionalLightFact] = Field(min_length=2, max_length=2)
    proposed_rig: list[ShotRigLight] = Field(min_length=3, max_length=3)
    output_stem: str = Field(pattern=r"^AF_[A-Za-z0-9_]{3,48}$")
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_request(self) -> BlenderShotRequest:
        if [light.role for light in self.proposed_rig] != ["key", "fill", "rim"]:
            raise ValueError("Blender shot rig roles must be key, fill and rim")
        if canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"})) != self.request_sha256:
            raise ValueError("Blender shot request fingerprint mismatch")
        return self


class BlenderShotArtifact(StrictContract):
    kind: Literal["blend", "preview"]
    relative_path: str = Field(pattern=r"^[A-Za-z0-9_./-]+$")
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class BlenderShotReceipt(StrictContract):
    schema_id: Literal["artflow-blender-shot-receipt/1"] = "artflow-blender-shot-receipt/1"
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.shot.rain_breakthrough.v1"]
    blender_version: str
    status: Literal["succeeded"] = "succeeded"
    camera_label: Literal["ArtFlow_Shot_Camera"]
    camera_location_error_cm: float = Field(ge=0, le=0.001)
    camera_fov_error_deg: float = Field(ge=0, le=0.001)
    light_count: int = Field(ge=3, le=3)
    unreal_rig: list[ShotRigLight] = Field(min_length=3, max_length=3)
    artifacts: list[BlenderShotArtifact] = Field(min_length=2, max_length=2)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderShotReceipt:
        if {item.kind for item in self.artifacts} != {"blend", "preview"}:
            raise ValueError("Blender shot receipt requires blend and preview artifacts")
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("Blender shot receipt fingerprint mismatch")
        return self


def compile_blender_shot_request(**values: object) -> BlenderShotRequest:
    unsigned = {
        "schema_id": "artflow-blender-shot-request/1",
        "capability_id": "blender.shot.rain_breakthrough.v1",
        "preset": "rain_breakthrough",
        **values,
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"blender-shot-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return BlenderShotRequest.model_validate(unsigned)


def execute_blender_shot(
    request: BlenderShotRequest,
    *,
    project_root: Path,
    output_dir: Path,
    blender_executable: Path,
    timeout_seconds: int = 180,
) -> BlenderShotReceipt:
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    if project_root not in output_dir.parents:
        raise ValueError("Blender output directory must stay inside the project")
    source_blend = project_root / "artifacts/goal/m23-s4-geometry-layout/AF_ShrineCourtyard_GN.blend"
    script = project_root / "integrations/blender/apply_camera_light_shot.py"
    if not source_blend.is_file() or not script.is_file() or not blender_executable.is_file():
        raise FileNotFoundError("Blender shot runtime dependency is missing")
    if hashlib.sha256(source_blend.read_bytes()).hexdigest() != request.source_blend_sha256:
        raise ValueError("Blender shot source identity mismatch")
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "shot-request.json"
    request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
    subprocess.run(
        [str(blender_executable), "--background", "--factory-startup", "--python", str(script), "--", str(request_path), str(output_dir), str(source_blend)],
        check=True,
        cwd=project_root,
        timeout=timeout_seconds,
    )
    receipt_path = output_dir / "shot-receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError("Blender exited without a shot receipt")
    receipt = BlenderShotReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("Blender shot receipt belongs to another request")
    for artifact in receipt.artifacts:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
            raise ValueError("Blender shot artifact identity mismatch")
    return receipt
