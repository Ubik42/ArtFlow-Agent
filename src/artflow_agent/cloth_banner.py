from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.comfy import ComfyGateway
from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ClothBannerRequest(StrictContract):
    schema_id: Literal["artflow-cloth-banner-request/1"] = "artflow-cloth-banner-request/1"
    request_id: str = Field(pattern=r"^cloth-banner-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    visual_target_path: str
    visual_target_sha256: str = Field(pattern=SHA256_PATTERN)
    protected_mask_path: str
    protected_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    attachment_actor: Literal["ArtFlow_Module_module-placement-05"]
    attachment_location_cm: tuple[float, float, float]
    width_m: float = Field(ge=1.0, le=4.0)
    height_m: float = Field(ge=1.5, le=6.0)
    wind_direction: tuple[float, float, float]
    wind_strength: float = Field(ge=100.0, le=1000.0)
    frame_end: int = Field(ge=24, le=96)
    mesh_columns: int = Field(ge=16, le=64)
    mesh_rows: int = Field(ge=24, le=96)
    triangle_budget: int = Field(ge=500, le=20_000)
    texture_resolution: Literal[512, 1024]
    seed: int = Field(ge=0, le=2**31 - 1)
    comfy_capability_id: Literal["comfy.material.banner_pattern.v1"]
    blender_capability_id: Literal["blender.cloth.banner_authoring.v1"]
    unreal_capability_id: Literal["unreal.asset.static_cloth_banner.v1"]
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> ClothBannerRequest:
        if canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"})) != self.request_sha256:
            raise ValueError("cloth banner request fingerprint mismatch")
        magnitude = sum(value * value for value in self.wind_direction) ** 0.5
        if not 0.99 <= magnitude <= 1.01:
            raise ValueError("wind direction must be normalized")
        return self


class BannerTextureReceipt(StrictContract):
    schema_id: Literal["artflow-comfy-banner-texture-receipt/1"]
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["comfy.material.banner_pattern.v1"]
    status: Literal["succeeded"]
    comfyui_version: str
    device: str
    provider_request_id: str
    observed_node_count: int = Field(gt=0)
    texture_path: str
    texture_sha256: str = Field(pattern=SHA256_PATTERN)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> BannerTextureReceipt:
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("banner texture receipt fingerprint mismatch")
        return self


def compile_cloth_banner_request(*, root: Path, session_id: str) -> ClothBannerRequest:
    root = root.resolve()
    source_receipt = json.loads(
        (root / "artifacts/goal/m55-s1-damage-variant/unreal-damage-variant-receipt.json").read_text(encoding="utf-8")
    )
    source_map = root / "integrations/unreal/ArtFlowBridgeHost/Content" / (
        source_receipt["candidate_scene_path"].removeprefix("/Game/") + ".umap"
    )
    visual = root / "artifacts/goal/m24-s1-scene-conditioning/depth-guided-candidate.png"
    protected = root / "artifacts/goal/m34-s1-pcg-density/protected-exclusion-mask.png"
    workflow_sha256 = canonical_sha256(
        {
            "recipe": "scene-banner-pattern-v1",
            "nodes": [
                "LoadImage", "ImageAddNoise", "ImageToMask", "ThresholdMask",
                "CreateShapeMask", "MaskComposite", "MaskToImage", "SaveImage",
                "WorkflowContractCheck", "ProductionConstraintCheck", "GenerationReceipt",
            ],
            "shape": "circle",
            "threshold": 0.56,
            "noise_strength": 0.32,
        }
    )
    payload = {
        "schema_id": "artflow-cloth-banner-request/1",
        "session_id": session_id,
        "source_candidate_scene_path": source_receipt["candidate_scene_path"],
        "source_candidate_sha256": file_sha256(source_map),
        "visual_target_path": visual.as_posix(),
        "visual_target_sha256": file_sha256(visual),
        "protected_mask_path": protected.as_posix(),
        "protected_mask_sha256": file_sha256(protected),
        "attachment_actor": "ArtFlow_Module_module-placement-05",
        "attachment_location_cm": [420.0, -155.0, 460.0],
        "width_m": 2.4,
        "height_m": 3.6,
        "wind_direction": [0.894427, 0.447214, 0.0],
        "wind_strength": 420.0,
        "frame_end": 48,
        "mesh_columns": 25,
        "mesh_rows": 37,
        "triangle_budget": 5000,
        "texture_resolution": 512,
        "seed": 570907,
        "comfy_capability_id": "comfy.material.banner_pattern.v1",
        "blender_capability_id": "blender.cloth.banner_authoring.v1",
        "unreal_capability_id": "unreal.asset.static_cloth_banner.v1",
        "workflow_sha256": workflow_sha256,
    }
    provisional = canonical_sha256(payload)
    payload["request_id"] = f"cloth-banner-{provisional[:16]}"
    payload["request_sha256"] = canonical_sha256(payload)
    return ClothBannerRequest.model_validate(payload)


def execute_banner_texture(
    request: ClothBannerRequest, *, output_dir: Path, comfy_url: str
) -> BannerTextureReceipt:
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "comfy-banner-texture-receipt.json"
    if receipt_path.is_file():
        existing = BannerTextureReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
        existing_texture = output_dir / existing.texture_path
        if existing.request_sha256 == request.request_sha256 and existing_texture.is_file() and file_sha256(existing_texture) == existing.texture_sha256:
            return existing
    visual = Path(request.visual_target_path)
    if file_sha256(visual) != request.visual_target_sha256:
        raise ValueError("registered banner visual target identity drifted")
    with ComfyGateway(comfy_url, timeout_seconds=20) as gateway:
        snapshot = gateway.inspect()
        required = {"ImageAddNoise", "CreateShapeMask", "WorkflowContractCheck", "ProductionConstraintCheck", "GenerationReceipt"}
        if not snapshot.reachable or not required <= set(snapshot.nodes):
            raise RuntimeError("registered ComfyUI banner capability is unavailable")
        folder = f"ArtFlow/{request.request_id}"
        uploaded = gateway.upload_image(visual, subfolder=folder, overwrite=True)
        image_name = f"{uploaded.subfolder}/{uploaded.name}"
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
            "2": {"class_type": "ImageAddNoise", "inputs": {"image": ["1", 0], "seed": request.seed, "strength": 0.32}},
            "3": {"class_type": "ImageToMask", "inputs": {"image": ["2", 0], "channel": "red"}},
            "4": {"class_type": "ThresholdMask", "inputs": {"mask": ["3", 0], "value": 0.56}},
            "5": {"class_type": "CreateShapeMask", "inputs": {"shape": "circle", "frames": 1, "location_x": 320, "location_y": 180, "grow": 0, "frame_width": 640, "frame_height": 360, "shape_width": 230, "shape_height": 230}},
            "6": {"class_type": "MaskComposite", "inputs": {"destination": ["4", 0], "source": ["5", 0], "x": 0, "y": 0, "operation": "add"}},
            "7": {"class_type": "MaskToImage", "inputs": {"mask": ["6", 0]}},
            "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": f"ArtFlow/{request.request_id}/banner-pattern"}},
            "9": {"class_type": "WorkflowContractCheck", "inputs": {"contract_json": json.dumps({"required_slots": ["visual_target"], "outputs": ["banner_pattern"]}), "workflow_values_json": json.dumps({"slots": {"visual_target": uploaded.name}, "parameters": {"seed": request.seed}})}},
            "10": {"class_type": "ProductionConstraintCheck", "inputs": {"width": 640, "height": 360, "batch_size": 1, "denoise": 0.0, "max_megapixels": 1.0, "max_batch_size": 1}},
            "11": {"class_type": "GenerationReceipt", "inputs": {"workflow_name": "scene-banner-pattern-v1", "model_name": "scene-conditioned-pattern", "lora_name": "none", "positive_prompt": "weathered heraldic textile pattern", "negative_prompt": "text, logo, camera change", "seed": request.seed}},
        }
        problems = gateway.validate_workflow(workflow)
        if problems:
            raise RuntimeError("banner workflow failed schema validation: " + "; ".join(problems))
        queued = gateway.queue(workflow)
        history = gateway.wait(queued.prompt_id, timeout_seconds=120, poll_seconds=0.25)
        output = next(item for item in gateway.collect_outputs(history) if item.node_id == "8")
        texture_path = output_dir / "T_AF_BannerPattern.png"
        gateway.download_output(output, texture_path)
    payload = {
        "schema_id": "artflow-comfy-banner-texture-receipt/1",
        "request_sha256": request.request_sha256,
        "capability_id": request.comfy_capability_id,
        "status": "succeeded",
        "comfyui_version": snapshot.comfyui_version or "unknown",
        "device": snapshot.device_name or "unknown",
        "provider_request_id": queued.prompt_id,
        "observed_node_count": len(snapshot.nodes),
        "texture_path": texture_path.name,
        "texture_sha256": file_sha256(texture_path),
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    receipt = BannerTextureReceipt.model_validate(payload)
    receipt_path.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return receipt


def execute_blender_cloth_banner(
    request: ClothBannerRequest, *, root: Path, output_dir: Path, blender_executable: Path
) -> dict[str, object]:
    request_path = output_dir / "cloth-banner-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    subprocess.run(
        [str(blender_executable), "--background", "--factory-startup", "--python", str(root / "integrations/blender/author_cloth_banner.py"), "--", str(request_path), str(output_dir)],
        cwd=root,
        check=True,
        timeout=360,
    )
    receipt_path = output_dir / "blender-cloth-banner-receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError("Blender did not produce a cloth banner receipt")
    return json.loads(receipt_path.read_text(encoding="utf-8"))
