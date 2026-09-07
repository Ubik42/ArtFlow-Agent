from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


class BlenderArchitecturalPropRequest(StrictContract):
    schema_id: Literal["artflow-blender-modeling-request/1"] = (
        "artflow-blender-modeling-request/1"
    )
    request_id: str = Field(pattern=r"^blender-model-[0-9a-f]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[0-9a-f]{12}$")
    session_sha256: str = Field(pattern=SHA256_PATTERN)
    source_scene: str = Field(pattern=r"^/Game/[A-Za-z0-9_/]+$")
    source_level_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.architectural_prop.weathered_shrine.v1"] = (
        "blender.architectural_prop.weathered_shrine.v1"
    )
    recipe: Literal["weathered_shrine"] = "weathered_shrine"
    width_cm: float = Field(ge=120, le=600)
    depth_cm: float = Field(ge=80, le=500)
    height_cm: float = Field(ge=120, le=700)
    tier_count: int = Field(ge=2, le=4)
    pillar_count: Literal[2, 4]
    detail_level: int = Field(ge=1, le=3)
    seed: int = Field(ge=0, le=2_147_483_647)
    palette: Literal["basalt_moss", "sandstone_ember", "limestone_rain"]
    output_stem: str = Field(pattern=r"^AF_[A-Za-z0-9_]{3,48}$")
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_hash(self) -> BlenderArchitecturalPropRequest:
        unsigned = self.model_dump(mode="json", exclude={"request_sha256"})
        if canonical_sha256(unsigned) != self.request_sha256:
            raise ValueError("Blender modeling request fingerprint mismatch")
        return self


class BlenderModelingArtifact(StrictContract):
    kind: Literal["blend", "glb", "preview"]
    relative_path: str = Field(pattern=r"^[A-Za-z0-9_./-]+$")
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class BlenderModelingReceipt(StrictContract):
    schema_id: Literal["artflow-blender-modeling-receipt/1"] = (
        "artflow-blender-modeling-receipt/1"
    )
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.architectural_prop.weathered_shrine.v1"]
    blender_version: str
    status: Literal["succeeded"] = "succeeded"
    object_count: int = Field(ge=1)
    mesh_count: int = Field(ge=1)
    vertex_count: int = Field(ge=3)
    triangle_count: int = Field(ge=1)
    material_count: int = Field(ge=1)
    bounds_cm: list[float] = Field(min_length=3, max_length=3)
    artifacts: list[BlenderModelingArtifact] = Field(min_length=3, max_length=3)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderModelingReceipt:
        if {item.kind for item in self.artifacts} != {"blend", "glb", "preview"}:
            raise ValueError("Blender receipt requires blend, glb and preview artifacts")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("Blender modeling receipt fingerprint mismatch")
        return self


def compile_weathered_shrine_request(**values: object) -> BlenderArchitecturalPropRequest:
    unsigned = {
        "schema_id": "artflow-blender-modeling-request/1",
        "capability_id": "blender.architectural_prop.weathered_shrine.v1",
        "recipe": "weathered_shrine",
        **values,
    }
    digest = canonical_sha256(unsigned)
    unsigned["request_id"] = f"blender-model-{digest[:16]}"
    normalized = BlenderArchitecturalPropRequest.model_construct(
        **unsigned, request_sha256="0" * 64
    ).model_dump(mode="json", exclude={"request_sha256"})
    unsigned["request_sha256"] = canonical_sha256(normalized)
    return BlenderArchitecturalPropRequest.model_validate(unsigned)


def execute_blender_modeling(
    request: BlenderArchitecturalPropRequest,
    *,
    project_root: Path,
    output_dir: Path,
    blender_executable: Path,
    timeout_seconds: int = 180,
) -> BlenderModelingReceipt:
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    if project_root not in output_dir.parents:
        raise ValueError("Blender output directory must stay inside the project")
    script = project_root / "integrations/blender/generate_architectural_prop.py"
    if not blender_executable.is_file() or not script.is_file():
        raise FileNotFoundError("Blender executable or registered modeling script is missing")
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "modeling-request.json"
    receipt_path = output_dir / "modeling-receipt.json"
    request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
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
        ],
        check=True,
        cwd=project_root,
        timeout=timeout_seconds,
    )
    if not receipt_path.is_file():
        raise RuntimeError("Blender exited without a modeling receipt")
    receipt = BlenderModelingReceipt.model_validate_json(
        receipt_path.read_text(encoding="utf-8")
    )
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("Blender receipt belongs to another modeling request")
    for artifact in receipt.artifacts:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir not in path.parents or not path.is_file():
            raise ValueError("Blender receipt references a missing output artifact")
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
            raise ValueError("Blender artifact hash mismatch")
    return receipt


def write_verified_receipt(
    payload: dict[str, object], *, completed_at: datetime
) -> BlenderModelingReceipt:
    payload["completed_at"] = completed_at
    unsigned = BlenderModelingReceipt.model_construct(
        **payload, receipt_sha256="0" * 64
    ).model_dump(mode="json", exclude={"receipt_sha256"})
    payload["receipt_sha256"] = canonical_sha256(unsigned)
    return BlenderModelingReceipt.model_validate(payload)
