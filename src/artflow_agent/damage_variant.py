from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.comfy import ComfyGateway
from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DamageVariantRequest(StrictContract):
    schema_id: Literal["artflow-damage-variant-request/1"] = (
        "artflow-damage-variant-request/1"
    )
    request_id: str = Field(pattern=r"^damage-variant-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blend_path: str
    source_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blender_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    depth_path: str
    depth_sha256: str = Field(pattern=SHA256_PATTERN)
    protected_mask_path: str
    protected_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    visual_target_path: str
    visual_target_sha256: str = Field(pattern=SHA256_PATTERN)
    target_module_id: Literal["gateway"]
    target_object: Literal["SM_AF_Module_Gateway"]
    target_actor_label: Literal["ArtFlow_Module_module-placement-05"]
    comfy_capability_id: Literal["comfy.spatial.damage_field.v1"]
    blender_capability_id: Literal["blender.boolean.material_damage.v1"]
    unreal_capability_id: Literal["unreal.asset.damage_variant.v1"]
    chip_count: int = Field(ge=4, le=12)
    damage_depth_m: float = Field(ge=0.04, le=0.24)
    mask_threshold: float = Field(ge=0.5, le=0.85)
    texture_resolution: Literal[512, 1024]
    triangle_budget: int = Field(ge=100, le=12_000)
    seed: int = Field(ge=0, le=2**31 - 1)
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> DamageVariantRequest:
        unsigned = self.model_dump(mode="json", exclude={"request_sha256"})
        if canonical_sha256(unsigned) != self.request_sha256:
            raise ValueError("damage variant request fingerprint mismatch")
        return self


class DamageFieldReceipt(StrictContract):
    schema_id: Literal["artflow-comfy-damage-field-receipt/1"]
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["comfy.spatial.damage_field.v1"]
    status: Literal["succeeded"]
    comfyui_version: str
    device: str
    provider_request_id: str
    observed_node_count: int = Field(gt=0)
    field_path: str
    field_sha256: str = Field(pattern=SHA256_PATTERN)
    active_coverage: float = Field(gt=0.002, lt=0.35)
    protected_leakage: float = Field(ge=0, le=0.01)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> DamageFieldReceipt:
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("damage field receipt fingerprint mismatch")
        return self


def compile_damage_variant_request(
    *, root: Path, session_id: str
) -> DamageVariantRequest:
    root = root.resolve()
    modular_root = root / "artifacts/goal/m47-s1-modular-environment"
    source_blend = modular_root / "AF_ModularEnvironment.blend"
    blender_receipt = json.loads(
        (modular_root / "blender-modular-environment-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    unreal_receipt = json.loads(
        (modular_root / "unreal-modular-environment-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    depth = root / "artifacts/goal/m24-s1-scene-conditioning/depth-normalized.png"
    protected = root / "artifacts/goal/m34-s1-pcg-density/protected-exclusion-mask.png"
    visual = root / "artifacts/goal/m24-s1-scene-conditioning/depth-guided-candidate.png"
    source_map = (
        root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / (unreal_receipt["candidate_scene_path"].removeprefix("/Game/") + ".umap")
    )
    workflow_sha256 = canonical_sha256(
        {
            "recipe": "scene-damage-field-v1",
            "nodes": [
                "LoadImage",
                "ImageAddNoise",
                "ImageToMask",
                "ThresholdMask",
                "CreateShapeMask",
                "MaskComposite:multiply",
                "LoadImage",
                "ImageToMask",
                "GrowMask",
                "MaskComposite:subtract",
                "MaskToImage",
                "SaveImage",
                "WorkflowContractCheck",
                "ProductionConstraintCheck",
                "GenerationReceipt",
            ],
            "target_region": [360, 72, 224, 244],
            "noise_strength": 0.72,
            "mask_threshold": 0.66,
        }
    )
    payload = {
        "schema_id": "artflow-damage-variant-request/1",
        "session_id": session_id,
        "source_candidate_scene_path": unreal_receipt["candidate_scene_path"],
        "source_candidate_sha256": file_sha256(source_map),
        "source_blend_path": source_blend.as_posix(),
        "source_blend_sha256": file_sha256(source_blend),
        "source_blender_receipt_sha256": blender_receipt["receipt_sha256"],
        "depth_path": depth.as_posix(),
        "depth_sha256": file_sha256(depth),
        "protected_mask_path": protected.as_posix(),
        "protected_mask_sha256": file_sha256(protected),
        "visual_target_path": visual.as_posix(),
        "visual_target_sha256": file_sha256(visual),
        "target_module_id": "gateway",
        "target_object": "SM_AF_Module_Gateway",
        "target_actor_label": "ArtFlow_Module_module-placement-05",
        "comfy_capability_id": "comfy.spatial.damage_field.v1",
        "blender_capability_id": "blender.boolean.material_damage.v1",
        "unreal_capability_id": "unreal.asset.damage_variant.v1",
        "chip_count": 7,
        "damage_depth_m": 0.14,
        "mask_threshold": 0.66,
        "texture_resolution": 512,
        "triangle_budget": 6000,
        "seed": 550907,
        "workflow_sha256": workflow_sha256,
    }
    provisional = canonical_sha256(payload)
    payload["request_id"] = f"damage-variant-{provisional[:16]}"
    payload["request_sha256"] = canonical_sha256(payload)
    return DamageVariantRequest.model_validate(payload)


def execute_damage_field(
    request: DamageVariantRequest, *, output_dir: Path, comfy_url: str
) -> DamageFieldReceipt:
    output_dir.mkdir(parents=True, exist_ok=True)
    depth = Path(request.depth_path)
    protected = Path(request.protected_mask_path)
    if (
        file_sha256(depth) != request.depth_sha256
        or file_sha256(protected) != request.protected_mask_sha256
    ):
        raise ValueError("registered damage conditioning identity drifted")
    with ComfyGateway(comfy_url, timeout_seconds=20) as gateway:
        snapshot = gateway.inspect()
        required = {
            "ImageAddNoise",
            "CreateShapeMask",
            "WorkflowContractCheck",
            "ProductionConstraintCheck",
            "GenerationReceipt",
        }
        if not snapshot.reachable or not required <= set(snapshot.nodes):
            raise RuntimeError("registered ComfyUI damage capability is unavailable")
        folder = f"ArtFlow/{request.request_id}"
        depth_upload = gateway.upload_image(depth, subfolder=folder, overwrite=True)
        protected_upload = gateway.upload_image(
            protected, subfolder=folder, overwrite=True
        )
        depth_name = f"{depth_upload.subfolder}/{depth_upload.name}"
        protected_name = f"{protected_upload.subfolder}/{protected_upload.name}"
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": depth_name}},
            "2": {
                "class_type": "ImageAddNoise",
                "inputs": {"image": ["1", 0], "seed": request.seed, "strength": 0.72},
            },
            "3": {
                "class_type": "ImageToMask",
                "inputs": {"image": ["2", 0], "channel": "red"},
            },
            "4": {
                "class_type": "ThresholdMask",
                "inputs": {"mask": ["3", 0], "value": request.mask_threshold},
            },
            "5": {
                "class_type": "CreateShapeMask",
                "inputs": {
                    "shape": "square",
                    "frames": 1,
                    "location_x": 472,
                    "location_y": 194,
                    "grow": 0,
                    "frame_width": 640,
                    "frame_height": 360,
                    "shape_width": 224,
                    "shape_height": 244,
                },
            },
            "6": {
                "class_type": "MaskComposite",
                "inputs": {
                    "destination": ["4", 0],
                    "source": ["5", 0],
                    "x": 0,
                    "y": 0,
                    "operation": "multiply",
                },
            },
            "7": {"class_type": "LoadImage", "inputs": {"image": protected_name}},
            "8": {
                "class_type": "ImageToMask",
                "inputs": {"image": ["7", 0], "channel": "red"},
            },
            "9": {
                "class_type": "GrowMask",
                "inputs": {"mask": ["8", 0], "expand": 12, "tapered_corners": True},
            },
            "10": {
                "class_type": "MaskComposite",
                "inputs": {
                    "destination": ["6", 0],
                    "source": ["9", 0],
                    "x": 0,
                    "y": 0,
                    "operation": "subtract",
                },
            },
            "11": {"class_type": "MaskToImage", "inputs": {"mask": ["10", 0]}},
            "12": {
                "class_type": "SaveImage",
                "inputs": {
                    "images": ["11", 0],
                    "filename_prefix": f"ArtFlow/{request.request_id}/damage-field",
                },
            },
            "13": {
                "class_type": "WorkflowContractCheck",
                "inputs": {
                    "contract_json": json.dumps(
                        {"required_slots": ["depth", "protected"], "outputs": ["damage_field"]}
                    ),
                    "workflow_values_json": json.dumps(
                        {
                            "slots": {"depth": depth_upload.name, "protected": protected_upload.name},
                            "parameters": {"threshold": request.mask_threshold},
                        }
                    ),
                },
            },
            "14": {
                "class_type": "ProductionConstraintCheck",
                "inputs": {
                    "width": 640,
                    "height": 360,
                    "batch_size": 1,
                    "denoise": 0.0,
                    "max_megapixels": 1.0,
                    "max_batch_size": 1,
                },
            },
            "15": {
                "class_type": "GenerationReceipt",
                "inputs": {
                    "workflow_name": "scene-damage-field-v1",
                    "model_name": "scene-conditioned-noise-mask",
                    "lora_name": "none",
                    "positive_prompt": "localized weathering and chipped stone damage field",
                    "negative_prompt": "protected scene center, camera drift, structural collapse",
                    "seed": request.seed,
                },
            },
        }
        problems = gateway.validate_workflow(workflow)
        if problems:
            raise RuntimeError(
                "damage-field workflow failed schema validation: " + "; ".join(problems)
            )
        queued = gateway.queue(workflow)
        history = gateway.wait(queued.prompt_id, timeout_seconds=120, poll_seconds=0.25)
        output = next(item for item in gateway.collect_outputs(history) if item.node_id == "12")
        field_path = output_dir / "damage-field.png"
        gateway.download_output(output, field_path)
    with Image.open(field_path) as field_image, Image.open(protected) as protected_image:
        values = list(field_image.convert("L").getdata())
        guards = list(protected_image.convert("L").resize(field_image.size).getdata())
    active = sum(value >= 128 for value in values)
    coverage = active / len(values)
    leakage = sum(
        value >= 128 and guard >= 128
        for value, guard in zip(values, guards, strict=True)
    ) / max(1, sum(guard >= 128 for guard in guards))
    if not 0.002 < coverage < 0.35 or leakage > 0.01:
        raise ValueError(
            f"damage field failed coverage/leakage: {coverage:.4f}/{leakage:.4f}"
        )
    payload = {
        "schema_id": "artflow-comfy-damage-field-receipt/1",
        "request_sha256": request.request_sha256,
        "capability_id": request.comfy_capability_id,
        "status": "succeeded",
        "comfyui_version": snapshot.comfyui_version or "unknown",
        "device": snapshot.device_name or "unknown",
        "provider_request_id": queued.prompt_id,
        "observed_node_count": len(snapshot.nodes),
        "field_path": field_path.name,
        "field_sha256": file_sha256(field_path),
        "active_coverage": round(coverage, 6),
        "protected_leakage": round(leakage, 6),
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    receipt = DamageFieldReceipt.model_validate(payload)
    (output_dir / "comfy-damage-field-receipt.json").write_text(
        receipt.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def execute_blender_damage(
    request: DamageVariantRequest,
    *,
    root: Path,
    output_dir: Path,
    blender_executable: Path,
) -> dict[str, object]:
    request_path = output_dir / "damage-variant-request.json"
    request_path.write_text(
        request.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    subprocess.run(
        [
            str(blender_executable),
            "--background",
            "--factory-startup",
            "--python",
            str(root / "integrations/blender/author_damage_variant.py"),
            "--",
            str(request_path),
            str(output_dir),
        ],
        cwd=root,
        check=True,
        timeout=360,
    )
    return json.loads(
        (output_dir / "blender-damage-variant-receipt.json").read_text(
            encoding="utf-8"
        )
    )
