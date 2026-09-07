from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


class SurfaceObject(StrictContract):
    name: str = Field(pattern=r"^AF_[A-Za-z0-9_-]{2,48}$")
    source: Literal["registered_mesh", "geometry_nodes_output"]


class BlenderSurfaceRequest(StrictContract):
    schema_id: Literal["artflow-blender-surface-request/1"] = (
        "artflow-blender-surface-request/1"
    )
    request_id: str = Field(pattern=r"^surface-bake-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    session_sha256: str = Field(pattern=SHA256_PATTERN)
    source_level_sha256: str = Field(pattern=SHA256_PATTERN)
    lookdev_request_sha256: str = Field(pattern=SHA256_PATTERN)
    lookdev_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.surface.uv_bake.v1"] = "blender.surface.uv_bake.v1"
    objects: list[SurfaceObject] = Field(min_length=2, max_length=32)
    uv_method: Literal["smart_project"] = "smart_project"
    uv_set: Literal["ArtFlow_BakedUV"] = "ArtFlow_BakedUV"
    atlas_resolution: Literal[1024] = 1024
    margin_px: int = Field(ge=8, le=32)
    bake_channels: list[Literal["base_color", "roughness"]] = Field(
        min_length=2, max_length=2
    )
    max_vertices: int = Field(ge=1_000, le=100_000)
    max_triangles: int = Field(ge=1_000, le=200_000)
    output_stem: Literal["AF_ShrineCourtyard_Baked"] = "AF_ShrineCourtyard_Baked"
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_request(self) -> BlenderSurfaceRequest:
        names = [item.name for item in self.objects]
        if len(names) != len(set(names)):
            raise ValueError("surface object scope contains duplicates")
        if self.bake_channels != ["base_color", "roughness"]:
            raise ValueError("surface bake channels must be base_color then roughness")
        if canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"})) != self.request_sha256:
            raise ValueError("surface request fingerprint mismatch")
        return self


class SurfaceArtifact(StrictContract):
    kind: Literal["blend", "glb", "preview", "base_color", "roughness"]
    relative_path: str = Field(pattern=r"^[A-Za-z0-9_./-]+$")
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class BlenderSurfaceReceipt(StrictContract):
    schema_id: Literal["artflow-blender-surface-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.surface.uv_bake.v1"]
    status: Literal["succeeded"]
    blender_version: str
    object_name: Literal["AF_ShrineCourtyard_Baked"]
    source_object_count: int = Field(ge=2, le=32)
    vertex_count: int = Field(gt=0, le=100_000)
    triangle_count: int = Field(gt=0, le=200_000)
    uv_set: Literal["ArtFlow_BakedUV"]
    uv_loop_count: int = Field(gt=0)
    uv_area_ratio: float = Field(gt=0, le=1)
    atlas_resolution: Literal[1024]
    material_slots: list[Literal["M_AF_BakedSurface"]] = Field(min_length=1, max_length=1)
    artifacts: list[SurfaceArtifact] = Field(min_length=5, max_length=5)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderSurfaceReceipt:
        if {item.kind for item in self.artifacts} != {
            "blend", "glb", "preview", "base_color", "roughness"
        }:
            raise ValueError("surface receipt is missing a required artifact")
        actual = canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"}))
        if actual != self.receipt_sha256:
            raise ValueError("surface receipt fingerprint mismatch")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_surface_request(
    *,
    session_id: str,
    session_sha256: str,
    source_level_sha256: str,
    lookdev_request_path: Path,
    lookdev_receipt_path: Path,
    source_blend_path: Path,
    objects: list[dict[str, str]],
) -> BlenderSurfaceRequest:
    lookdev_request = json.loads(lookdev_request_path.read_text(encoding="utf-8"))
    lookdev_receipt = json.loads(lookdev_receipt_path.read_text(encoding="utf-8"))
    if lookdev_receipt["request_sha256"] != lookdev_request["request_sha256"]:
        raise ValueError("lookdev request and receipt do not match")
    if file_sha256(source_blend_path) != next(
        item["sha256"] for item in lookdev_receipt["artifacts"] if item["kind"] == "blend"
    ):
        raise ValueError("lookdev blend identity drifted")
    unsigned = {
        "schema_id": "artflow-blender-surface-request/1",
        "session_id": session_id,
        "session_sha256": session_sha256,
        "source_level_sha256": source_level_sha256,
        "lookdev_request_sha256": lookdev_request["request_sha256"],
        "lookdev_receipt_sha256": file_sha256(lookdev_receipt_path),
        "source_blend_sha256": file_sha256(source_blend_path),
        "capability_id": "blender.surface.uv_bake.v1",
        "objects": objects,
        "uv_method": "smart_project",
        "uv_set": "ArtFlow_BakedUV",
        "atlas_resolution": 1024,
        "margin_px": 16,
        "bake_channels": ["base_color", "roughness"],
        "max_vertices": 50_000,
        "max_triangles": 100_000,
        "output_stem": "AF_ShrineCourtyard_Baked",
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"surface-bake-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return BlenderSurfaceRequest.model_validate(unsigned)


def verify_surface_artifacts(
    request: BlenderSurfaceRequest,
    receipt: BlenderSurfaceReceipt,
    output_dir: Path,
) -> None:
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("surface receipt belongs to another request")
    for artifact in receipt.artifacts:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir.resolve() not in path.parents:
            raise ValueError("surface artifact escaped output directory")
        if file_sha256(path) != artifact.sha256 or path.stat().st_size != artifact.size_bytes:
            raise ValueError(f"surface artifact identity mismatch: {artifact.kind}")
        if artifact.kind in {"base_color", "roughness"}:
            with Image.open(path) as image:
                if image.size != (request.atlas_resolution, request.atlas_resolution):
                    raise ValueError(f"surface texture dimensions mismatch: {artifact.kind}")
    if receipt.vertex_count > request.max_vertices or receipt.triangle_count > request.max_triangles:
        raise ValueError("surface geometry exceeds the registered budget")


def execute_surface_bake(
    request: BlenderSurfaceRequest,
    *,
    project_root: Path,
    source_blend_path: Path,
    output_dir: Path,
    blender_executable: Path,
    timeout_seconds: int = 300,
) -> BlenderSurfaceReceipt:
    project_root, output_dir = project_root.resolve(), output_dir.resolve()
    if project_root not in output_dir.parents:
        raise ValueError("surface output must stay inside the project")
    if file_sha256(source_blend_path) != request.source_blend_sha256:
        raise ValueError("surface source blend identity mismatch")
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "surface-request.json"
    request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
    script = project_root / "integrations/blender/bake_scene_surface.py"
    subprocess.run(
        [str(blender_executable), "--background", "--factory-startup", "--python", str(script),
         "--", str(request_path), str(output_dir), str(source_blend_path)],
        check=True,
        cwd=project_root,
        timeout=timeout_seconds,
    )
    if not (output_dir / "surface-receipt.json").is_file():
        raise RuntimeError("Blender exited without a surface receipt")
    receipt = BlenderSurfaceReceipt.model_validate_json(
        (output_dir / "surface-receipt.json").read_text(encoding="utf-8")
    )
    verify_surface_artifacts(request, receipt, output_dir)
    return receipt
