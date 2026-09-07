from __future__ import annotations

import hashlib
import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw
from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.comfy import ComfyGateway
from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


class ScreenRect(StrictContract):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class PcgDensityRequest(StrictContract):
    schema_id: Literal["artflow-pcg-density-request/1"] = "artflow-pcg-density-request/1"
    request_id: str = Field(pattern=r"^pcg-density-[a-f0-9]{16}$")
    session_id: str
    scene_package_sha256: str = Field(pattern=SHA256_PATTERN)
    depth_path: str
    depth_sha256: str = Field(pattern=SHA256_PATTERN)
    protected_regions: list[ScreenRect] = Field(min_length=1, max_length=8)
    kit_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    kit_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    comfy_capability_id: Literal["comfy.pcg_density.depth_exclusion.v1"]
    unreal_consumer_capability_id: Literal["unreal.pcg.native_density_kit.v1"]
    recipe_id: Literal["pcg-density-depth-exclusion-v1"]
    recipe_version: Literal["1.0.0"]
    threshold: float = Field(ge=0.1, le=0.9)
    exclusion_expand_px: int = Field(ge=0, le=64)
    seed: int = Field(ge=0, le=2**31 - 1)
    width: int = Field(ge=64, le=4096)
    height: int = Field(ge=64, le=4096)
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> PcgDensityRequest:
        if canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"})) != self.request_sha256:
            raise ValueError("PCG density request fingerprint mismatch")
        return self


class PcgDensityReceipt(StrictContract):
    schema_id: Literal["artflow-pcg-density-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["comfy.pcg_density.depth_exclusion.v1"]
    status: Literal["succeeded"]
    comfyui_version: str
    device: str
    observed_node_count: int = Field(gt=0)
    production_nodes: list[str] = Field(min_length=3, max_length=3)
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    provider_request_id: str
    density_mask_path: str
    density_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    protected_mask_path: str
    protected_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    spatial_manifest_path: str
    spatial_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    width: int
    height: int
    active_pixel_coverage: float = Field(gt=0, lt=1)
    exclusion_leakage: float = Field(ge=0, le=0.01)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> PcgDensityReceipt:
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("PCG density receipt fingerprint mismatch")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _workflow_template_hash(threshold: float, expand: int) -> str:
    return canonical_sha256(
        {
            "recipe": "pcg-density-depth-exclusion-v1",
            "nodes": ["LoadImage", "ImageToMask", "ThresholdMask", "LoadImage", "ImageToMask",
                      "GrowMask", "MaskComposite", "GrowMask", "MaskToImage", "SaveImage",
                      "WorkflowContractCheck", "ProductionConstraintCheck", "GenerationReceipt"],
            "threshold": threshold,
            "exclusion_expand_px": expand,
        }
    )


def compile_pcg_density_request(
    *, session_id: str, scene_package_sha256: str, depth_path: Path,
    kit_receipt_path: Path, kit_manifest_path: Path,
) -> PcgDensityRequest:
    with Image.open(depth_path) as image:
        width, height = image.size
    kit_receipt = json.loads(kit_receipt_path.read_text(encoding="utf-8"))
    manifest_artifact = next(item for item in kit_receipt["artifacts"] if item["kind"] == "manifest")
    if file_sha256(kit_manifest_path) != manifest_artifact["sha256"]:
        raise ValueError("registered procedural-kit manifest identity drifted")
    unsigned = {
        "schema_id": "artflow-pcg-density-request/1", "session_id": session_id,
        "scene_package_sha256": scene_package_sha256, "depth_path": depth_path.resolve().as_posix(),
        "depth_sha256": file_sha256(depth_path),
        "protected_regions": [
            {"x": 116, "y": 108, "width": 186, "height": 252},
            {"x": 348, "y": 132, "width": 142, "height": 132},
            {"x": 478, "y": 0, "width": 162, "height": 252},
        ],
        "kit_receipt_sha256": kit_receipt["receipt_sha256"],
        "kit_manifest_sha256": manifest_artifact["sha256"],
        "comfy_capability_id": "comfy.pcg_density.depth_exclusion.v1",
        "unreal_consumer_capability_id": "unreal.pcg.native_density_kit.v1",
        "recipe_id": "pcg-density-depth-exclusion-v1", "recipe_version": "1.0.0",
        "threshold": 0.42, "exclusion_expand_px": 12, "seed": 340907,
        "width": width, "height": height,
        "workflow_sha256": _workflow_template_hash(0.42, 12),
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"pcg-density-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return PcgDensityRequest.model_validate(unsigned)


def _workflow(request: PcgDensityRequest, depth_name: str, protected_name: str) -> dict[str, object]:
    contract = {"required_slots": ["depth", "protected"], "parameter_ranges": {"threshold": [0.1, 0.9]}}
    values = {"slots": {"depth": depth_name, "protected": protected_name}, "parameters": {"threshold": request.threshold}}
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": depth_name}},
        "2": {"class_type": "ImageToMask", "inputs": {"image": ["1", 0], "channel": "red"}},
        "3": {"class_type": "ThresholdMask", "inputs": {"mask": ["2", 0], "value": request.threshold}},
        "4": {"class_type": "LoadImage", "inputs": {"image": protected_name}},
        "5": {"class_type": "ImageToMask", "inputs": {"image": ["4", 0], "channel": "red"}},
        "6": {"class_type": "GrowMask", "inputs": {"mask": ["5", 0], "expand": request.exclusion_expand_px, "tapered_corners": True}},
        "7": {"class_type": "MaskComposite", "inputs": {"destination": ["3", 0], "source": ["6", 0], "x": 0, "y": 0, "operation": "subtract"}},
        "8": {"class_type": "GrowMask", "inputs": {"mask": ["7", 0], "expand": -2, "tapered_corners": True}},
        "9": {"class_type": "MaskToImage", "inputs": {"mask": ["8", 0]}},
        "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": f"ArtFlow/{request.request_id}/pcg-density"}},
        "11": {"class_type": "WorkflowContractCheck", "inputs": {"contract_json": json.dumps(contract), "workflow_values_json": json.dumps(values)}},
        "12": {"class_type": "ProductionConstraintCheck", "inputs": {"width": request.width, "height": request.height, "batch_size": 1, "denoise": 0.0, "max_megapixels": 1.0, "max_batch_size": 1}},
        "13": {"class_type": "GenerationReceipt", "inputs": {"workflow_name": request.recipe_id, "model_name": "deterministic-mask-nodes", "lora_name": "none", "positive_prompt": "scene depth density outside protected actors", "negative_prompt": "protected actors", "seed": request.seed}},
    }


def execute_pcg_density(request: PcgDensityRequest, *, output_dir: Path, comfy_url: str) -> PcgDensityReceipt:
    output_dir.mkdir(parents=True, exist_ok=True)
    depth_path = Path(request.depth_path)
    if file_sha256(depth_path) != request.depth_sha256:
        raise ValueError("registered depth identity drifted")
    protected_path = output_dir / "protected-exclusion-mask.png"
    protected = Image.new("L", (request.width, request.height), 0)
    draw = ImageDraw.Draw(protected)
    for rect in request.protected_regions:
        draw.rectangle((rect.x, rect.y, rect.x + rect.width, rect.y + rect.height), fill=255)
    protected.save(protected_path)
    with ComfyGateway(comfy_url, timeout_seconds=20) as gateway:
        snapshot = gateway.inspect()
        required = {"WorkflowContractCheck", "ProductionConstraintCheck", "GenerationReceipt"}
        if not snapshot.reachable or not required <= set(snapshot.nodes):
            raise RuntimeError("registered ComfyUI density capability is unavailable")
        subfolder = f"ArtFlow/{request.request_id}"
        depth_upload = gateway.upload_image(depth_path, subfolder=subfolder, overwrite=True)
        protected_upload = gateway.upload_image(protected_path, subfolder=subfolder, overwrite=True)
        depth_name = f"{depth_upload.subfolder}/{depth_upload.name}"
        protected_name = f"{protected_upload.subfolder}/{protected_upload.name}"
        workflow = _workflow(request, depth_name, protected_name)
        problems = gateway.validate_workflow(workflow)
        if problems:
            raise RuntimeError("density workflow failed schema validation: " + "; ".join(problems))
        queued = gateway.queue(workflow)
        history = gateway.wait(queued.prompt_id, timeout_seconds=120, poll_seconds=0.25)
        outputs = [item for item in gateway.collect_outputs(history) if item.node_id == "10"]
        if len(outputs) != 1:
            raise RuntimeError("density workflow did not return exactly one mask")
        mask_path = output_dir / "pcg-density-mask.png"
        gateway.download_output(outputs[0], mask_path)
    with Image.open(mask_path) as mask_image, Image.open(protected_path) as protected_image:
        mask = mask_image.convert("L")
        protection = protected_image.convert("L")
        if mask.size != (request.width, request.height):
            raise ValueError("density mask dimensions changed")
        pixels = list(mask.getdata())
        protection_pixels = list(protection.getdata())
        active = sum(value >= 128 for value in pixels)
        protected_active = sum(value >= 128 and guard >= 128 for value, guard in zip(pixels, protection_pixels, strict=True))
        coverage = active / len(pixels)
        leakage = protected_active / max(1, sum(value >= 128 for value in protection_pixels))
    if not 0.05 <= coverage <= 0.75 or leakage > 0.01:
        raise ValueError(f"density mask failed coverage/leakage checks: {coverage:.4f}/{leakage:.4f}")
    candidates = [
        (index % request.width, index // request.width)
        for index, value in enumerate(pixels)
        if value >= 128
    ]
    rng = random.Random(request.seed)
    rng.shuffle(candidates)
    selected: list[tuple[int, int]] = []
    for pixel in candidates:
        if all(math.dist(pixel, other) >= 46 for other in selected):
            selected.append(pixel)
        if len(selected) == 12:
            break
    if len(selected) != 12:
        raise ValueError("density mask cannot provide twelve separated native PCG points")
    points = []
    for index, (x, y) in enumerate(selected):
        points.append(
            {
                "point_id": f"density-point-{index + 1:02d}",
                "pixel_uv": [x, y],
                "location_cm": [
                    round((x / (request.width - 1) - 0.5) * 900, 3),
                    round((0.5 - y / (request.height - 1)) * 900, 3),
                    20.0,
                ],
                "yaw_deg": round((index * 137.508) % 360, 3),
                "scale": round(0.72 + (index % 4) * 0.08, 3),
                "density": round(pixels[y * request.width + x] / 255, 4),
                "seed": request.seed + index,
            }
        )
    spatial = {
        "schema_id": "artflow-pcg-density-spatial-manifest/1",
        "request_sha256": request.request_sha256,
        "coordinate_system": "unreal-centimeters-z-up",
        "projection": "screen-mask-to-registered-courtyard-bounds-v1",
        "native_graph_template": "/Game/ArtFlow/PCG/PCG_ArtFlowScatter.PCG_ArtFlowScatter",
        "points": points,
    }
    spatial["manifest_sha256"] = canonical_sha256(spatial)
    spatial_path = output_dir / "pcg-density-points.json"
    spatial_path.write_text(json.dumps(spatial, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    payload = {
        "schema_id": "artflow-pcg-density-receipt/1", "request_id": request.request_id,
        "request_sha256": request.request_sha256, "capability_id": request.comfy_capability_id,
        "status": "succeeded", "comfyui_version": snapshot.comfyui_version or "unknown",
        "device": snapshot.device_name or "unknown", "observed_node_count": len(snapshot.nodes),
        "production_nodes": sorted(required), "workflow_sha256": request.workflow_sha256,
        "provider_request_id": queued.prompt_id, "density_mask_path": mask_path.name,
        "density_mask_sha256": file_sha256(mask_path), "protected_mask_path": protected_path.name,
        "protected_mask_sha256": file_sha256(protected_path), "width": request.width, "height": request.height,
        "spatial_manifest_path": spatial_path.name, "spatial_manifest_sha256": file_sha256(spatial_path),
        "active_pixel_coverage": round(coverage, 6), "exclusion_leakage": round(leakage, 6),
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    receipt = PcgDensityReceipt.model_validate(payload)
    (output_dir / "pcg-density-receipt.json").write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return receipt
