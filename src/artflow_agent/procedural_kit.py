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


class KitBounds(StrictContract):
    min_m: list[float] = Field(min_length=3, max_length=3)
    max_m: list[float] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_bounds(self) -> KitBounds:
        values = [*self.min_m, *self.max_m]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("kit bounds must be finite")
        if any(low >= high for low, high in zip(self.min_m, self.max_m, strict=True)):
            raise ValueError("kit bounds are inverted")
        return self


class ProceduralKitRequest(StrictContract):
    schema_id: Literal["artflow-procedural-kit-request/1"] = "artflow-procedural-kit-request/1"
    request_id: str = Field(pattern=r"^procedural-kit-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    session_sha256: str = Field(pattern=SHA256_PATTERN)
    source_level_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    visual_target_path: str
    visual_target_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.geometry_nodes.modular_wayfinder_kit.v1"]
    consumer_capability_id: Literal["unreal.pcg.modular_kit_scatter.v1"]
    kit_family: Literal["oxidized-wayfinder"]
    variant_count: Literal[3]
    bounds: KitBounds
    placement_count: int = Field(ge=6, le=24)
    seed: int = Field(ge=0, le=2**31 - 1)
    material_slots: list[Literal["M_AF_Stone", "M_AF_GeneratedInlay"]] = Field(
        min_length=2, max_length=2
    )
    lod_policy: Literal["lod1-at-most-60-percent-triangles"]
    collision_policy: Literal["explicit-box-proxy-per-variant"]
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> ProceduralKitRequest:
        actual = canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"}))
        if actual != self.request_sha256:
            raise ValueError("procedural kit request fingerprint mismatch")
        return self


class KitVariant(StrictContract):
    variant_id: str = Field(pattern=r"^wayfinder-[abc]$")
    object_name: str = Field(pattern=r"^SM_AF_Wayfinder_[ABC]$")
    base_glb: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.glb$")
    base_sha256: str = Field(pattern=SHA256_PATTERN)
    lod1_glb: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.glb$")
    lod1_sha256: str = Field(pattern=SHA256_PATTERN)
    base_triangles: int = Field(gt=0)
    lod1_triangles: int = Field(gt=0)
    uv_layers: list[Literal["UVMap"]] = Field(min_length=1, max_length=1)
    material_slots: list[str] = Field(min_length=2, max_length=2)
    collision_kind: Literal["box"]
    collision_extent_m: list[float] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_lod(self) -> KitVariant:
        if self.lod1_triangles > self.base_triangles * 0.6:
            raise ValueError("LOD1 exceeds registered triangle ratio")
        if not all(value > 0 and math.isfinite(value) for value in self.collision_extent_m):
            raise ValueError("collision extent must be positive and finite")
        return self


class PlacementPoint(StrictContract):
    point_id: str = Field(pattern=r"^kit-point-[0-9]{2}$")
    variant_id: str = Field(pattern=r"^wayfinder-[abc]$")
    location_m: list[float] = Field(min_length=3, max_length=3)
    yaw_deg: float
    scale: float = Field(ge=0.8, le=1.25)


class KitArtifact(StrictContract):
    kind: Literal["blend", "preview", "manifest"]
    relative_path: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class ProceduralKitReceipt(StrictContract):
    schema_id: Literal["artflow-procedural-kit-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.geometry_nodes.modular_wayfinder_kit.v1"]
    status: Literal["succeeded"]
    blender_version: str
    variants: list[KitVariant] = Field(min_length=3, max_length=3)
    placements: list[PlacementPoint] = Field(min_length=6, max_length=24)
    artifacts: list[KitArtifact] = Field(min_length=3, max_length=3)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> ProceduralKitReceipt:
        if {item.variant_id for item in self.variants} != {
            "wayfinder-a", "wayfinder-b", "wayfinder-c"
        }:
            raise ValueError("procedural kit must contain the three registered variants")
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("procedural kit receipt fingerprint mismatch")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_procedural_kit_request(
    *, session_id: str, session_sha256: str, source_level_sha256: str,
    source_candidate_scene_path: str, visual_target_path: Path, bounds_path: Path,
) -> ProceduralKitRequest:
    bounds_request = json.loads(bounds_path.read_text(encoding="utf-8"))
    visual_target_path = visual_target_path.resolve()
    unsigned = {
        "schema_id": "artflow-procedural-kit-request/1",
        "session_id": session_id,
        "session_sha256": session_sha256,
        "source_level_sha256": source_level_sha256,
        "source_candidate_scene_path": source_candidate_scene_path,
        "visual_target_path": visual_target_path.as_posix(),
        "visual_target_sha256": file_sha256(visual_target_path),
        "capability_id": "blender.geometry_nodes.modular_wayfinder_kit.v1",
        "consumer_capability_id": "unreal.pcg.modular_kit_scatter.v1",
        "kit_family": "oxidized-wayfinder",
        "variant_count": 3,
        "bounds": {
            "min_m": [float(value) for value in bounds_request["bounds"]["min_m"]],
            "max_m": [float(value) for value in bounds_request["bounds"]["max_m"]],
        },
        "placement_count": 9,
        "seed": 320907,
        "material_slots": ["M_AF_Stone", "M_AF_GeneratedInlay"],
        "lod_policy": "lod1-at-most-60-percent-triangles",
        "collision_policy": "explicit-box-proxy-per-variant",
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"procedural-kit-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return ProceduralKitRequest.model_validate(unsigned)


def verify_procedural_kit(
    request: ProceduralKitRequest, receipt: ProceduralKitReceipt, output_dir: Path
) -> None:
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("procedural kit receipt belongs to another request")
    low, high = request.bounds.min_m, request.bounds.max_m
    for point in receipt.placements:
        if not all(low[i] <= point.location_m[i] <= high[i] for i in range(3)):
            raise ValueError(f"placement escaped registered bounds: {point.point_id}")
    for variant in receipt.variants:
        for relative, expected in ((variant.base_glb, variant.base_sha256), (variant.lod1_glb, variant.lod1_sha256)):
            path = (output_dir / relative).resolve()
            if output_dir.resolve() not in path.parents or file_sha256(path) != expected:
                raise ValueError(f"kit mesh identity mismatch: {relative}")
    for artifact in receipt.artifacts:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir.resolve() not in path.parents or file_sha256(path) != artifact.sha256:
            raise ValueError(f"kit artifact identity mismatch: {artifact.kind}")


def execute_procedural_kit(
    request: ProceduralKitRequest, *, project_root: Path, output_dir: Path,
    blender_executable: Path, timeout_seconds: int = 300,
) -> ProceduralKitReceipt:
    project_root, output_dir = project_root.resolve(), output_dir.resolve()
    if project_root not in output_dir.parents:
        raise ValueError("procedural kit output must stay inside the project")
    visual = Path(request.visual_target_path)
    if file_sha256(visual) != request.visual_target_sha256:
        raise ValueError("visual target identity drifted")
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "procedural-kit-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    script = project_root / "integrations/blender/generate_procedural_kit.py"
    subprocess.run(
        [str(blender_executable), "--background", "--factory-startup", "--python", str(script),
         "--", str(request_path), str(output_dir)],
        check=True, cwd=project_root, timeout=timeout_seconds,
    )
    receipt_path = output_dir / "procedural-kit-receipt.json"
    receipt = ProceduralKitReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    verify_procedural_kit(request, receipt, output_dir)
    return receipt
