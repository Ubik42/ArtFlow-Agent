from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


class BlenderGeometryLayoutRequest(StrictContract):
    schema_id: Literal["artflow-blender-geometry-layout-request/1"] = (
        "artflow-blender-geometry-layout-request/1"
    )
    request_id: str = Field(pattern=r"^blender-layout-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    session_sha256: str = Field(pattern=SHA256_PATTERN)
    source_level_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    pbr_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.geometry_nodes.shrine_courtyard.v1"] = (
        "blender.geometry_nodes.shrine_courtyard.v1"
    )
    layout_style: Literal["shrine_courtyard"] = "shrine_courtyard"
    radius_cm: float = Field(ge=360, le=900)
    support_count: int = Field(ge=6, le=24)
    height_variation: float = Field(ge=0.0, le=0.45)
    seed: int = Field(ge=0, le=2_147_483_647)
    output_stem: str = Field(pattern=r"^AF_[A-Za-z0-9_]{3,48}$")
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_hash(self) -> BlenderGeometryLayoutRequest:
        if canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"})) != self.request_sha256:
            raise ValueError("Blender Geometry Nodes request fingerprint mismatch")
        return self


class BlenderGeometryLayoutArtifact(StrictContract):
    kind: Literal["blend", "glb", "preview"]
    relative_path: str = Field(pattern=r"^[A-Za-z0-9_./-]+$")
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class BlenderGeometryLayoutReceipt(StrictContract):
    schema_id: Literal["artflow-blender-geometry-layout-receipt/1"] = (
        "artflow-blender-geometry-layout-receipt/1"
    )
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.geometry_nodes.shrine_courtyard.v1"]
    blender_version: str
    status: Literal["succeeded"] = "succeeded"
    node_group: Literal["AF_GN_ShrineCourtyard_v1"]
    support_element_count: int = Field(ge=6, le=24)
    prototype_count: int = Field(ge=3, le=3)
    realized_vertex_count: int = Field(gt=0)
    realized_triangle_count: int = Field(gt=0)
    bounds_cm: list[float] = Field(min_length=3, max_length=3)
    artifacts: list[BlenderGeometryLayoutArtifact] = Field(min_length=3, max_length=3)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderGeometryLayoutReceipt:
        if {item.kind for item in self.artifacts} != {"blend", "glb", "preview"}:
            raise ValueError("Geometry Nodes receipt requires blend, glb and preview artifacts")
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("Blender Geometry Nodes receipt fingerprint mismatch")
        return self


def compile_geometry_layout_request(**values: object) -> BlenderGeometryLayoutRequest:
    unsigned = {
        "schema_id": "artflow-blender-geometry-layout-request/1",
        "capability_id": "blender.geometry_nodes.shrine_courtyard.v1",
        "layout_style": "shrine_courtyard",
        **values,
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"blender-layout-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return BlenderGeometryLayoutRequest.model_validate(unsigned)


def execute_geometry_layout(
    request: BlenderGeometryLayoutRequest,
    *,
    project_root: Path,
    output_dir: Path,
    blender_executable: Path,
    timeout_seconds: int = 180,
) -> BlenderGeometryLayoutReceipt:
    project_root = project_root.resolve()
    output_dir = output_dir.resolve()
    if project_root not in output_dir.parents:
        raise ValueError("Blender output directory must stay inside the project")
    script = project_root / "integrations/blender/generate_geometry_layout.py"
    source_blend = project_root / "artifacts/goal/m23-s2-blender-pbr/AF_WeatheredShrine_PBR.blend"
    if not blender_executable.is_file() or not script.is_file() or not source_blend.is_file():
        raise FileNotFoundError("Geometry Nodes runtime dependency is missing")
    if hashlib.sha256(source_blend.read_bytes()).hexdigest() != request.source_blend_sha256:
        raise ValueError("Geometry Nodes source blend identity mismatch")
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "layout-request.json"
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
            str(source_blend),
        ],
        check=True,
        cwd=project_root,
        timeout=timeout_seconds,
    )
    receipt_path = output_dir / "layout-receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError("Blender exited without a Geometry Nodes receipt")
    receipt = BlenderGeometryLayoutReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("Geometry Nodes receipt belongs to another request")
    for artifact in receipt.artifacts:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != artifact.sha256:
            raise ValueError("Geometry Nodes artifact identity mismatch")
    return receipt
