from __future__ import annotations

import hashlib
import json
import math
import struct
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


class ImageTo3DGenerationRequest(StrictContract):
    schema_id: Literal["image-to-3d-generation-request/1"] = "image-to-3d-generation-request/1"
    request_id: str = Field(pattern=r"^m10-mesh-[0-9a-f]{20}$")
    source_artifact_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    source_image_sha256: str = Field(pattern=SHA256_PATTERN)
    provider_id: Literal["stabilityai-triposr-space"]
    model_id: Literal["stabilityai/TripoSR"]
    provider_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    license_spdx: Literal["MIT"]
    license_sha256: str = Field(pattern=SHA256_PATTERN)
    license_source_url: Literal[
        "https://raw.githubusercontent.com/VAST-AI-Research/TripoSR/main/LICENSE"
    ]
    output_format: Literal["glb"] = "glb"
    remove_background: bool = True
    foreground_ratio: float = Field(ge=0.5, le=1.0)
    marching_cubes_resolution: int = Field(ge=32, le=320, multiple_of=32)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_hash(self) -> ImageTo3DGenerationRequest:
        unsigned = self.model_dump(mode="json", exclude={"request_sha256"})
        if canonical_sha256(unsigned) != self.request_sha256:
            raise ValueError("image-to-3D request fingerprint mismatch")
        return self


class ImageTo3DGenerationReceipt(StrictContract):
    schema_id: Literal["image-to-3d-generation-receipt/1"] = "image-to-3d-generation-receipt/1"
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    provider_id: Literal["stabilityai-triposr-space"]
    model_id: Literal["stabilityai/TripoSR"]
    provider_endpoint: Literal["https://stabilityai-triposr.hf.space"]
    status: Literal["succeeded"] = "succeeded"
    processed_image_sha256: str = Field(pattern=SHA256_PATTERN)
    glb_sha256: str = Field(pattern=SHA256_PATTERN)
    glb_size_bytes: int = Field(gt=0)
    external_submission_count: Literal[1] = 1
    estimated_cost_usd: Literal[0.0] = 0.0
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_hash(self) -> ImageTo3DGenerationReceipt:
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("image-to-3D receipt fingerprint mismatch")
        return self


class MeshAdmissionPolicy(StrictContract):
    schema_id: Literal["mesh-admission-policy/1"] = "mesh-admission-policy/1"
    policy_id: Literal["artflow-generated-prop-v1"] = "artflow-generated-prop-v1"
    max_file_bytes: int = Field(default=20_000_000, ge=1)
    max_vertices: int = Field(default=100_000, ge=3)
    max_triangles: int = Field(default=150_000, ge=1)
    min_longest_extent: float = Field(default=0.1, gt=0)
    max_longest_extent: float = Field(default=10.0, gt=0)
    target_longest_extent_cm: float = Field(default=180.0, ge=10, le=1000)
    allow_vertex_color_material: bool = True
    allow_generated_normals: bool = True
    allowed_extensions: list[str] = Field(default_factory=list, max_length=8)


class GLBInspectionReceipt(StrictContract):
    schema_id: Literal["glb-inspection-receipt/1"] = "glb-inspection-receipt/1"
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    generation_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["admitted", "rejected"]
    rejection_reasons: list[str]
    file_size_bytes: int = Field(gt=0)
    mesh_count: int = Field(ge=0)
    primitive_count: int = Field(ge=0)
    vertex_count: int = Field(ge=0)
    triangle_count: int = Field(ge=0)
    material_count: int = Field(ge=0)
    embedded_buffer_count: int = Field(ge=0)
    external_uri_count: int = Field(ge=0)
    unsupported_extensions: list[str]
    bounds_min: list[float] | None
    bounds_max: list[float] | None
    longest_extent: float | None
    unreal_uniform_scale: float | None
    material_strategy: Literal["pbr_material", "vertex_color_engine_material", "missing"]
    normals_strategy: Literal["source", "generate_in_unreal", "missing"]
    collision_strategy: Literal["generate_simple_after_import"]
    inspected_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_result(self) -> GLBInspectionReceipt:
        if (self.status == "admitted") == bool(self.rejection_reasons):
            raise ValueError("admission status and rejection reasons disagree")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("GLB inspection fingerprint mismatch")
        return self


class UnrealMeshAdmissionRequest(StrictContract):
    schema_id: Literal["unreal-mesh-admission-request/1"] = "unreal-mesh-admission-request/1"
    request_id: str = Field(pattern=r"^m10-unreal-[0-9a-f]{20}$")
    generation_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    inspection_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_relative_path: Literal[
        "artifacts/goal/m10-s2-image-to-3d/altar-triposr.glb"
    ]
    candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    destination_root: str = Field(pattern=r"^/Game/ArtFlow/Generated/m10_[0-9a-f]{12}$")
    asset_name: Literal["SM_AF_GeneratedAltar"]
    target_longest_extent_cm: float = Field(ge=10, le=1000)
    unreal_uniform_scale: float = Field(gt=0)
    material_strategy: Literal["vertex_color_engine_material"]
    normals_strategy: Literal["generate_in_unreal"]
    collision_strategy: Literal["generate_simple_after_import"]
    authority_scope: Literal["project_local_unreal_fixture"]
    source_scene_sha256: str = Field(pattern=SHA256_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_hash(self) -> UnrealMeshAdmissionRequest:
        unsigned = self.model_dump(mode="json", exclude={"request_sha256"})
        if canonical_sha256(unsigned) != self.request_sha256:
            raise ValueError("Unreal mesh admission request fingerprint mismatch")
        return self


class UnrealMeshAdmissionReceipt(StrictContract):
    schema_id: Literal["unreal-mesh-admission-receipt/1"] = "unreal-mesh-admission-receipt/1"
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["imported", "reconciled"]
    engine_version: str
    static_mesh_path: str
    imported_object_paths: list[str] = Field(min_length=1)
    vertex_count: int = Field(ge=3)
    triangle_count: int = Field(ge=1)
    material_slot_count: int = Field(ge=1)
    simple_collision_count: int = Field(ge=1)
    bounds_extent_cm: list[float] = Field(min_length=3, max_length=3)
    source_scene_sha256_before: str = Field(pattern=SHA256_PATTERN)
    source_scene_sha256_after: str = Field(pattern=SHA256_PATTERN)
    duplicate_side_effect_count: int = Field(ge=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_result(self) -> UnrealMeshAdmissionReceipt:
        if self.source_scene_sha256_before != self.source_scene_sha256_after:
            raise ValueError("source scene changed during generated mesh admission")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("Unreal mesh admission receipt fingerprint mismatch")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_glb(
    path: Path,
    request: ImageTo3DGenerationRequest,
    generation: ImageTo3DGenerationReceipt,
    policy: MeshAdmissionPolicy,
    *,
    inspected_at: datetime,
) -> GLBInspectionReceipt:
    data = path.read_bytes()
    reasons: list[str] = []
    document: dict[str, Any] = {}
    embedded_buffers = 0
    if len(data) < 20:
        reasons.append("glb_too_short")
    else:
        magic, version, declared_length = struct.unpack_from("<4sII", data, 0)
        if magic != b"glTF" or version != 2 or declared_length != len(data):
            reasons.append("invalid_glb_header")
        cursor = 12
        json_chunks = 0
        while cursor + 8 <= len(data):
            chunk_length, chunk_type = struct.unpack_from("<I4s", data, cursor)
            cursor += 8
            end = cursor + chunk_length
            if end > len(data):
                reasons.append("truncated_glb_chunk")
                break
            chunk = data[cursor:end]
            if chunk_type == b"JSON":
                json_chunks += 1
                try:
                    document = json.loads(chunk.rstrip(b" \x00"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    reasons.append("invalid_glb_json")
            elif chunk_type == b"BIN\x00":
                embedded_buffers += 1
            cursor = end
        if json_chunks != 1:
            reasons.append("glb_requires_one_json_chunk")
        if cursor != len(data):
            reasons.append("glb_chunk_alignment_mismatch")

    meshes = document.get("meshes", []) if isinstance(document.get("meshes", []), list) else []
    accessors = (
        document.get("accessors", []) if isinstance(document.get("accessors", []), list) else []
    )
    buffers = document.get("buffers", []) if isinstance(document.get("buffers", []), list) else []
    images = document.get("images", []) if isinstance(document.get("images", []), list) else []
    extensions = document.get("extensionsUsed", [])
    if not isinstance(extensions, list):
        extensions = []
        reasons.append("invalid_extensions_used")
    unsupported_extensions = sorted(set(extensions) - set(policy.allowed_extensions))
    if unsupported_extensions:
        reasons.append("unsupported_glb_extensions")
    external_uri_count = sum("uri" in item for item in buffers + images if isinstance(item, dict))
    if external_uri_count:
        reasons.append("external_uri_forbidden")
    if document.get("asset", {}).get("version") != "2.0":
        reasons.append("unsupported_gltf_version")
    if len(data) > policy.max_file_bytes:
        reasons.append("file_budget_exceeded")

    primitive_count = 0
    vertex_count = 0
    triangle_count = 0
    position_mins: list[list[float]] = []
    position_maxs: list[list[float]] = []
    all_have_material = True
    all_have_vertex_color = True
    all_have_normals = True
    for mesh in meshes:
        for primitive in mesh.get("primitives", []):
            primitive_count += 1
            attributes = primitive.get("attributes", {})
            position_index = attributes.get("POSITION")
            if not isinstance(position_index, int) or not 0 <= position_index < len(accessors):
                reasons.append("missing_position_accessor")
                continue
            position = accessors[position_index]
            count = int(position.get("count", 0))
            vertex_count += count
            if position.get("type") != "VEC3" or count < 3:
                reasons.append("invalid_position_accessor")
            minimum, maximum = position.get("min"), position.get("max")
            if _finite_vec3(minimum) and _finite_vec3(maximum):
                position_mins.append(minimum)
                position_maxs.append(maximum)
            else:
                reasons.append("position_bounds_missing")
            index = primitive.get("indices")
            index_count = accessors[index].get("count", 0) if isinstance(index, int) else count
            if primitive.get("mode", 4) != 4 or index_count % 3:
                reasons.append("non_triangle_primitive")
            else:
                triangle_count += int(index_count) // 3
            all_have_material &= isinstance(primitive.get("material"), int)
            all_have_vertex_color &= "COLOR_0" in attributes
            all_have_normals &= "NORMAL" in attributes

    if not meshes or not primitive_count:
        reasons.append("mesh_missing")
    if vertex_count > policy.max_vertices:
        reasons.append("vertex_budget_exceeded")
    if triangle_count > policy.max_triangles:
        reasons.append("triangle_budget_exceeded")

    material_count = len(document.get("materials", []))
    if all_have_material and material_count:
        material_strategy = "pbr_material"
    elif all_have_vertex_color and policy.allow_vertex_color_material:
        material_strategy = "vertex_color_engine_material"
    else:
        material_strategy = "missing"
        reasons.append("material_representation_missing")
    if all_have_normals:
        normals_strategy = "source"
    elif policy.allow_generated_normals:
        normals_strategy = "generate_in_unreal"
    else:
        normals_strategy = "missing"
        reasons.append("normals_missing")

    bounds_min = [min(values) for values in zip(*position_mins, strict=True)] if position_mins else None
    bounds_max = [max(values) for values in zip(*position_maxs, strict=True)] if position_maxs else None
    longest_extent = None
    unreal_scale = None
    if bounds_min and bounds_max:
        extents = [high - low for low, high in zip(bounds_min, bounds_max, strict=True)]
        longest_extent = max(extents)
        if not policy.min_longest_extent <= longest_extent <= policy.max_longest_extent:
            reasons.append("source_scale_out_of_bounds")
        elif longest_extent > 0:
            # glTF meters are converted to Unreal centimeters by Interchange. This is the
            # actor-level scale needed after that standard unit conversion.
            unreal_scale = policy.target_longest_extent_cm / (longest_extent * 100.0)

    payload: dict[str, Any] = {
        "request_sha256": request.request_sha256,
        "generation_receipt_sha256": generation.receipt_sha256,
        "candidate_sha256": file_sha256(path),
        "status": "rejected" if reasons else "admitted",
        "rejection_reasons": sorted(set(reasons)),
        "file_size_bytes": len(data),
        "mesh_count": len(meshes),
        "primitive_count": primitive_count,
        "vertex_count": vertex_count,
        "triangle_count": triangle_count,
        "material_count": material_count,
        "embedded_buffer_count": embedded_buffers,
        "external_uri_count": external_uri_count,
        "unsupported_extensions": unsupported_extensions,
        "bounds_min": bounds_min,
        "bounds_max": bounds_max,
        "longest_extent": longest_extent,
        "unreal_uniform_scale": unreal_scale,
        "material_strategy": material_strategy,
        "normals_strategy": normals_strategy,
        "collision_strategy": "generate_simple_after_import",
        "inspected_at": inspected_at,
    }
    payload["receipt_sha256"] = canonical_sha256(
        GLBInspectionReceipt.model_construct(**payload, receipt_sha256="0" * 64).model_dump(
            mode="json", exclude={"receipt_sha256"}
        )
    )
    return GLBInspectionReceipt(**payload)


def _finite_vec3(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 3
        and all(isinstance(item, int | float) and math.isfinite(item) for item in value)
    )
