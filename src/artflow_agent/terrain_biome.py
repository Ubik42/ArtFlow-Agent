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


class TerrainBounds(StrictContract):
    width_cm: int = Field(ge=400, le=4000)
    depth_cm: int = Field(ge=400, le=4000)
    height_cm: int = Field(ge=20, le=500)


class TerrainBiomeRequest(StrictContract):
    schema_id: Literal["artflow-terrain-biome-request/1"] = "artflow-terrain-biome-request/1"
    request_id: str = Field(pattern=r"^terrain-biome-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    depth_path: str
    depth_sha256: str = Field(pattern=SHA256_PATTERN)
    protected_mask_path: str
    protected_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    material_candidate_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    comfy_capability_id: Literal["comfy.terrain.height_biome_fields.v1"]
    blender_capability_id: Literal["blender.geometry_nodes.bounded_terrain.v1"]
    unreal_capability_id: Literal["unreal.pcg.biome_terrain_candidate.v1"]
    recipe_id: Literal["terrain-height-biome-v1"]
    bounds: TerrainBounds
    grid_x: int = Field(ge=24, le=128)
    grid_y: int = Field(ge=16, le=128)
    biome_threshold: float = Field(ge=0.2, le=0.8)
    seed: int = Field(ge=0, le=2**31 - 1)
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> TerrainBiomeRequest:
        actual = canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"}))
        if actual != self.request_sha256:
            raise ValueError("terrain request fingerprint mismatch")
        return self


class TerrainFieldReceipt(StrictContract):
    schema_id: Literal["artflow-comfy-terrain-fields-receipt/1"]
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["comfy.terrain.height_biome_fields.v1"]
    status: Literal["succeeded"]
    comfyui_version: str
    device: str
    observed_node_count: int = Field(gt=0)
    provider_request_id: str
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    height_map_path: str
    height_map_sha256: str = Field(pattern=SHA256_PATTERN)
    biome_mask_path: str
    biome_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    width: int
    height: int
    biome_coverage: float = Field(gt=0.03, lt=0.9)
    protected_leakage: float = Field(ge=0, le=0.01)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> TerrainFieldReceipt:
        actual = canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"}))
        if actual != self.receipt_sha256:
            raise ValueError("terrain field receipt fingerprint mismatch")
        return self


def _workflow_hash(threshold: float) -> str:
    return canonical_sha256({
        "recipe": "terrain-height-biome-v1",
        "nodes": ["LoadImage", "ImageToMask", "GrowMask", "MaskToImage", "SaveImage",
                  "ThresholdMask", "LoadImage", "ImageToMask", "GrowMask", "MaskComposite",
                  "MaskToImage", "SaveImage", "WorkflowContractCheck",
                  "ProductionConstraintCheck", "GenerationReceipt"],
        "biome_threshold": threshold,
    })


def compile_terrain_biome_request(*, depth_path: Path, protected_mask_path: Path,
                                   material_receipt_path: Path,
                                   session_id: str) -> TerrainBiomeRequest:
    material = json.loads(material_receipt_path.read_text(encoding="utf-8"))
    if material.get("status") not in {"applied", "reconciled"}:
        raise ValueError("terrain route requires the completed material candidate")
    if file_sha256(depth_path) == file_sha256(protected_mask_path):
        raise ValueError("depth and protection inputs must be independent")
    unsigned = {
        "schema_id": "artflow-terrain-biome-request/1", "session_id": session_id,
        "depth_path": depth_path.resolve().as_posix(), "depth_sha256": file_sha256(depth_path),
        "protected_mask_path": protected_mask_path.resolve().as_posix(),
        "protected_mask_sha256": file_sha256(protected_mask_path),
        "material_candidate_receipt_sha256": file_sha256(material_receipt_path),
        "source_candidate_scene_path": material["candidate_scene_path"],
        "comfy_capability_id": "comfy.terrain.height_biome_fields.v1",
        "blender_capability_id": "blender.geometry_nodes.bounded_terrain.v1",
        "unreal_capability_id": "unreal.pcg.biome_terrain_candidate.v1",
        "recipe_id": "terrain-height-biome-v1", "bounds": {"width_cm": 1600, "depth_cm": 1200, "height_cm": 180},
        "grid_x": 64, "grid_y": 48, "biome_threshold": 0.56, "seed": 420907,
        "workflow_sha256": _workflow_hash(0.56),
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"terrain-biome-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return TerrainBiomeRequest.model_validate(unsigned)


def _workflow(request: TerrainBiomeRequest, depth: str, protected: str) -> dict[str, object]:
    contract = {"required_slots": ["depth", "protected"], "outputs": ["height", "biome"]}
    values = {"slots": {"depth": depth, "protected": protected}, "parameters": {"threshold": request.biome_threshold}}
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": depth}},
        "2": {"class_type": "ImageToMask", "inputs": {"image": ["1", 0], "channel": "red"}},
        "3": {"class_type": "GrowMask", "inputs": {"mask": ["2", 0], "expand": -2, "tapered_corners": True}},
        "4": {"class_type": "MaskToImage", "inputs": {"mask": ["3", 0]}},
        "5": {"class_type": "SaveImage", "inputs": {"images": ["4", 0], "filename_prefix": f"ArtFlow/{request.request_id}/terrain-height"}},
        "6": {"class_type": "ThresholdMask", "inputs": {"mask": ["3", 0], "value": request.biome_threshold}},
        "7": {"class_type": "LoadImage", "inputs": {"image": protected}},
        "8": {"class_type": "ImageToMask", "inputs": {"image": ["7", 0], "channel": "red"}},
        "9": {"class_type": "GrowMask", "inputs": {"mask": ["8", 0], "expand": 10, "tapered_corners": True}},
        "10": {"class_type": "MaskComposite", "inputs": {"destination": ["6", 0], "source": ["9", 0], "x": 0, "y": 0, "operation": "subtract"}},
        "11": {"class_type": "MaskToImage", "inputs": {"mask": ["10", 0]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": f"ArtFlow/{request.request_id}/biome-mask"}},
        "13": {"class_type": "WorkflowContractCheck", "inputs": {"contract_json": json.dumps(contract), "workflow_values_json": json.dumps(values)}},
        "14": {"class_type": "ProductionConstraintCheck", "inputs": {"width": 640, "height": 360, "batch_size": 1, "denoise": 0.0, "max_megapixels": 1.0, "max_batch_size": 1}},
        "15": {"class_type": "GenerationReceipt", "inputs": {"workflow_name": request.recipe_id, "model_name": "deterministic-spatial-nodes", "lora_name": "none", "positive_prompt": "bounded terrain height and biome fields", "negative_prompt": "protected scene center", "seed": request.seed}},
    }


def execute_terrain_fields(request: TerrainBiomeRequest, *, output_dir: Path,
                           comfy_url: str) -> TerrainFieldReceipt:
    output_dir.mkdir(parents=True, exist_ok=True)
    depth_path, protected_path = Path(request.depth_path), Path(request.protected_mask_path)
    if file_sha256(depth_path) != request.depth_sha256 or file_sha256(protected_path) != request.protected_mask_sha256:
        raise ValueError("registered terrain input identity drifted")
    with ComfyGateway(comfy_url, timeout_seconds=20) as gateway:
        snapshot = gateway.inspect()
        required = {"WorkflowContractCheck", "ProductionConstraintCheck", "GenerationReceipt"}
        if not snapshot.reachable or not required <= set(snapshot.nodes):
            raise RuntimeError("registered ComfyUI terrain capability is unavailable")
        subfolder = f"ArtFlow/{request.request_id}"
        depth_upload = gateway.upload_image(depth_path, subfolder=subfolder, overwrite=True)
        protected_upload = gateway.upload_image(protected_path, subfolder=subfolder, overwrite=True)
        workflow = _workflow(request, f"{depth_upload.subfolder}/{depth_upload.name}", f"{protected_upload.subfolder}/{protected_upload.name}")
        problems = gateway.validate_workflow(workflow)
        if problems:
            raise RuntimeError("terrain workflow failed schema validation: " + "; ".join(problems))
        queued = gateway.queue(workflow)
        history = gateway.wait(queued.prompt_id, timeout_seconds=120, poll_seconds=0.25)
        outputs = {item.node_id: item for item in gateway.collect_outputs(history) if item.node_id in {"5", "12"}}
        if set(outputs) != {"5", "12"}:
            raise RuntimeError("terrain workflow did not return both registered fields")
        height_path, biome_path = output_dir / "terrain-height.png", output_dir / "biome-mask.png"
        gateway.download_output(outputs["5"], height_path)
        gateway.download_output(outputs["12"], biome_path)
    with Image.open(height_path) as height_image, Image.open(biome_path) as biome_image, Image.open(protected_path) as protected_image:
        height = height_image.convert("L")
        biome = biome_image.convert("L")
        protection = protected_image.convert("L").resize(biome.size)
        pixels, guards = list(biome.getdata()), list(protection.getdata())
        coverage = sum(v >= 128 for v in pixels) / len(pixels)
        leakage = sum(v >= 128 and g >= 128 for v, g in zip(pixels, guards, strict=True)) / max(1, sum(g >= 128 for g in guards))
        width, image_height = height.size
    if not 0.03 < coverage < 0.9 or leakage > 0.01:
        raise ValueError(f"terrain fields failed coverage/leakage: {coverage:.4f}/{leakage:.4f}")
    payload = {"schema_id": "artflow-comfy-terrain-fields-receipt/1", "request_sha256": request.request_sha256,
               "capability_id": request.comfy_capability_id, "status": "succeeded",
               "comfyui_version": snapshot.comfyui_version or "unknown", "device": snapshot.device_name or "unknown",
               "observed_node_count": len(snapshot.nodes), "provider_request_id": queued.prompt_id,
               "workflow_sha256": request.workflow_sha256, "height_map_path": height_path.name,
               "height_map_sha256": file_sha256(height_path), "biome_mask_path": biome_path.name,
               "biome_mask_sha256": file_sha256(biome_path), "width": width, "height": image_height,
               "biome_coverage": round(coverage, 6), "protected_leakage": round(leakage, 6),
               "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    payload["receipt_sha256"] = canonical_sha256(payload)
    receipt = TerrainFieldReceipt.model_validate(payload)
    (output_dir / "comfy-terrain-fields-receipt.json").write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return receipt


def execute_blender_terrain(request: TerrainBiomeRequest, *, project_root: Path,
                            output_dir: Path, blender_executable: Path) -> dict[str, object]:
    request_path = output_dir / "terrain-biome-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    subprocess.run([str(blender_executable), "--background", "--factory-startup", "--python",
                    str(project_root / "integrations/blender/author_biome_terrain.py"), "--",
                    str(request_path), str(output_dir)], check=True, cwd=project_root, timeout=360)
    receipt_path = output_dir / "blender-terrain-receipt.json"
    return json.loads(receipt_path.read_text(encoding="utf-8"))
