from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MaterialPalette(StrictContract):
    variant_id: Literal["wayfinder-a", "wayfinder-b", "wayfinder-c"]
    object_name: str = Field(pattern=r"^SM_AF_Wayfinder_[ABC]$")
    material_name: str = Field(pattern=r"^M_AF_Wayfinder_[ABC]_SceneVariant$")
    base_tint: list[float] = Field(min_length=3, max_length=3)
    roughness: float = Field(ge=0.2, le=0.9)
    metallic: float = Field(ge=0.0, le=0.8)
    emission_strength: float = Field(ge=0.0, le=0.35)

    @model_validator(mode="after")
    def validate_tint(self) -> MaterialPalette:
        if not all(0.0 <= value <= 1.0 for value in self.base_tint):
            raise ValueError("material tint must stay in normalized RGB range")
        if self.variant_id[-1].upper() != self.object_name[-1]:
            raise ValueError("material palette and object variant differ")
        return self


class MaterialVariationRequest(StrictContract):
    schema_id: Literal["artflow-material-variation-request/1"] = (
        "artflow-material-variation-request/1"
    )
    request_id: str = Field(pattern=r"^material-variation-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    session_sha256: str = Field(pattern=SHA256_PATTERN)
    conditioning_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    visual_target_path: str
    visual_target_sha256: str = Field(pattern=SHA256_PATTERN)
    kit_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    kit_blend_path: str
    kit_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    native_pcg_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    capability_id: Literal["blender.material.scene_conditioned_wayfinder_set.v1"]
    consumer_capability_id: Literal["unreal.material.pcg_variant_instances.v1"]
    texture_size: Literal[512]
    bake_channels: list[Literal["base_color", "roughness"]] = Field(min_length=2, max_length=2)
    palettes: list[MaterialPalette] = Field(min_length=3, max_length=3)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> MaterialVariationRequest:
        if [item.variant_id for item in self.palettes] != [
            "wayfinder-a",
            "wayfinder-b",
            "wayfinder-c",
        ]:
            raise ValueError("material request requires the registered A/B/C variants")
        if self.bake_channels != ["base_color", "roughness"]:
            raise ValueError("material request requires the registered bake channels")
        actual = canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"}))
        if actual != self.request_sha256:
            raise ValueError("material variation request fingerprint mismatch")
        return self


class MaterialVariantResult(StrictContract):
    variant_id: Literal["wayfinder-a", "wayfinder-b", "wayfinder-c"]
    object_name: str
    material_name: str
    uv_layer: Literal["UVMap"]
    uv_coverage: float = Field(gt=0.45, le=1.0)
    shader_node_count: int = Field(ge=4)
    base_color_texture: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.png$")
    base_color_sha256: str = Field(pattern=SHA256_PATTERN)
    roughness_texture: str = Field(pattern=r"^[A-Za-z0-9_.-]+\.png$")
    roughness_sha256: str = Field(pattern=SHA256_PATTERN)


class MaterialVariationArtifact(StrictContract):
    kind: Literal["blend", "preview"]
    relative_path: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class BlenderMaterialVariationReceipt(StrictContract):
    schema_id: Literal["artflow-blender-material-variation-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.material.scene_conditioned_wayfinder_set.v1"]
    status: Literal["succeeded"]
    blender_version: str
    variants: list[MaterialVariantResult] = Field(min_length=3, max_length=3)
    artifacts: list[MaterialVariationArtifact] = Field(min_length=2, max_length=2)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderMaterialVariationReceipt:
        if [item.variant_id for item in self.variants] != [
            "wayfinder-a",
            "wayfinder-b",
            "wayfinder-c",
        ]:
            raise ValueError("material receipt requires all three variants")
        actual = canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"}))
        if actual != self.receipt_sha256:
            raise ValueError("material variation receipt fingerprint mismatch")
        return self


def compile_material_variation_request(
    *,
    conditioning_receipt_path: Path,
    procedural_kit_receipt_path: Path,
    native_pcg_receipt_path: Path,
    session_id: str,
    session_sha256: str,
) -> MaterialVariationRequest:
    conditioning = json.loads(conditioning_receipt_path.read_text(encoding="utf-8"))
    kit = json.loads(procedural_kit_receipt_path.read_text(encoding="utf-8"))
    pcg = json.loads(native_pcg_receipt_path.read_text(encoding="utf-8"))
    if conditioning.get("status") != "succeeded" or kit.get("status") != "succeeded":
        raise ValueError("material variation requires successful ComfyUI and Blender inputs")
    if pcg.get("status") not in {"generated", "reconciled"}:
        raise ValueError("material variation requires a completed native PCG candidate")

    conditioning_root = conditioning_receipt_path.resolve().parent
    visual_target = conditioning_root / conditioning["artifact_path"]
    kit_root = procedural_kit_receipt_path.resolve().parent
    blend_artifact = next(item for item in kit["artifacts"] if item["kind"] == "blend")
    kit_blend = kit_root / blend_artifact["relative_path"]
    if file_sha256(visual_target) != conditioning["artifact_sha256"]:
        raise ValueError("registered ComfyUI visual target identity drifted")
    if file_sha256(kit_blend) != blend_artifact["sha256"]:
        raise ValueError("registered Wayfinder blend identity drifted")

    palettes = [
        {
            "variant_id": "wayfinder-a",
            "object_name": "SM_AF_Wayfinder_A",
            "material_name": "M_AF_Wayfinder_A_SceneVariant",
            "base_tint": [0.42, 0.78, 0.72],
            "roughness": 0.38,
            "metallic": 0.48,
            "emission_strength": 0.12,
        },
        {
            "variant_id": "wayfinder-b",
            "object_name": "SM_AF_Wayfinder_B",
            "material_name": "M_AF_Wayfinder_B_SceneVariant",
            "base_tint": [0.88, 0.48, 0.24],
            "roughness": 0.56,
            "metallic": 0.34,
            "emission_strength": 0.08,
        },
        {
            "variant_id": "wayfinder-c",
            "object_name": "SM_AF_Wayfinder_C",
            "material_name": "M_AF_Wayfinder_C_SceneVariant",
            "base_tint": [0.34, 0.46, 0.82],
            "roughness": 0.7,
            "metallic": 0.22,
            "emission_strength": 0.05,
        },
    ]
    unsigned = {
        "schema_id": "artflow-material-variation-request/1",
        "session_id": session_id,
        "session_sha256": session_sha256,
        "conditioning_receipt_sha256": file_sha256(conditioning_receipt_path),
        "visual_target_path": visual_target.as_posix(),
        "visual_target_sha256": file_sha256(visual_target),
        "kit_receipt_sha256": file_sha256(procedural_kit_receipt_path),
        "kit_blend_path": kit_blend.as_posix(),
        "kit_blend_sha256": file_sha256(kit_blend),
        "native_pcg_receipt_sha256": file_sha256(native_pcg_receipt_path),
        "source_candidate_scene_path": pcg["candidate_scene_path"],
        "capability_id": "blender.material.scene_conditioned_wayfinder_set.v1",
        "consumer_capability_id": "unreal.material.pcg_variant_instances.v1",
        "texture_size": 512,
        "bake_channels": ["base_color", "roughness"],
        "palettes": palettes,
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"material-variation-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return MaterialVariationRequest.model_validate(unsigned)


def verify_material_variation(
    request: MaterialVariationRequest,
    receipt: BlenderMaterialVariationReceipt,
    output_dir: Path,
) -> None:
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("material receipt belongs to another request")
    for variant in receipt.variants:
        for relative, expected in (
            (variant.base_color_texture, variant.base_color_sha256),
            (variant.roughness_texture, variant.roughness_sha256),
        ):
            path = (output_dir / relative).resolve()
            if output_dir.resolve() not in path.parents or file_sha256(path) != expected:
                raise ValueError(f"material texture identity mismatch: {relative}")
    for artifact in receipt.artifacts:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir.resolve() not in path.parents or file_sha256(path) != artifact.sha256:
            raise ValueError(f"material artifact identity mismatch: {artifact.kind}")


def execute_material_variation(
    request: MaterialVariationRequest,
    *,
    project_root: Path,
    output_dir: Path,
    blender_executable: Path,
    timeout_seconds: int = 360,
) -> BlenderMaterialVariationReceipt:
    project_root, output_dir = project_root.resolve(), output_dir.resolve()
    if project_root not in output_dir.parents:
        raise ValueError("material variation output must stay inside the project")
    if file_sha256(Path(request.visual_target_path)) != request.visual_target_sha256:
        raise ValueError("ComfyUI visual target identity drifted")
    if file_sha256(Path(request.kit_blend_path)) != request.kit_blend_sha256:
        raise ValueError("Wayfinder blend identity drifted")
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "material-variation-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    script = project_root / "integrations/blender/author_material_variations.py"
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
    receipt_path = output_dir / "blender-material-variation-receipt.json"
    receipt = BlenderMaterialVariationReceipt.model_validate_json(
        receipt_path.read_text(encoding="utf-8")
    )
    verify_material_variation(request, receipt, output_dir)
    return receipt
