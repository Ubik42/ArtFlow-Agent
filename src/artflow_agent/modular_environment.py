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


class ModuleSpec(StrictContract):
    module_id: Literal["wall", "pillar", "gateway"]
    max_count: int = Field(ge=2, le=8)
    width_cm: int = Field(ge=80, le=500)
    depth_cm: int = Field(ge=30, le=200)
    height_cm: int = Field(ge=120, le=600)


class ModularEnvironmentRequest(StrictContract):
    schema_id: Literal["artflow-modular-environment-request/1"] = "artflow-modular-environment-request/1"
    request_id: str = Field(pattern=r"^modular-environment-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    depth_path: str
    depth_sha256: str = Field(pattern=SHA256_PATTERN)
    protected_mask_path: str
    protected_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    visual_target_path: str
    visual_target_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    comfy_capability_id: Literal["comfy.spatial.module_zones.v1"]
    blender_capability_id: Literal["blender.geometry_nodes.modular_environment.v1"]
    unreal_capability_id: Literal["unreal.actors.modular_environment.v1"]
    modules: list[ModuleSpec] = Field(min_length=3, max_length=3)
    placement_budget: int = Field(ge=6, le=24)
    triangle_budget: int = Field(ge=100, le=10000)
    seed: int = Field(ge=0, le=2**31 - 1)
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> ModularEnvironmentRequest:
        if {item.module_id for item in self.modules} != {"wall", "pillar", "gateway"}:
            raise ValueError("modular environment requires the registered module catalog")
        if canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"})) != self.request_sha256:
            raise ValueError("modular environment request fingerprint mismatch")
        return self


class ModuleZoneReceipt(StrictContract):
    schema_id: Literal["artflow-comfy-module-zone-receipt/1"]
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["comfy.spatial.module_zones.v1"]
    status: Literal["succeeded"]
    comfyui_version: str
    device: str
    provider_request_id: str
    observed_node_count: int = Field(gt=0)
    zone_map_path: str
    zone_map_sha256: str = Field(pattern=SHA256_PATTERN)
    zone_coverage: float = Field(gt=0.02, lt=0.95)
    protected_leakage: float = Field(ge=0, le=0.01)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> ModuleZoneReceipt:
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("module-zone receipt fingerprint mismatch")
        return self


def compile_modular_environment_request(*, root: Path, session_id: str) -> ModularEnvironmentRequest:
    root = root.resolve()
    depth = root / "artifacts/goal/m24-s1-scene-conditioning/depth-normalized.png"
    protected = root / "artifacts/goal/m34-s1-pcg-density/protected-exclusion-mask.png"
    visual = root / "artifacts/goal/m24-s1-scene-conditioning/depth-guided-candidate.png"
    foliage = json.loads((root / "artifacts/goal/m45-s1-foliage-kit/unreal-biome-foliage-receipt.json").read_text(encoding="utf-8"))
    source = root / "integrations/unreal/ArtFlowBridgeHost/Content" / (foliage["candidate_scene_path"].removeprefix("/Game/") + ".umap")
    workflow = canonical_sha256({"recipe": "module-zones-v1", "nodes": ["LoadImage", "ImageToMask", "GrowMask", "ThresholdMask", "LoadImage", "ImageToMask", "GrowMask", "MaskComposite", "MaskToImage", "SaveImage", "WorkflowContractCheck", "ProductionConstraintCheck", "GenerationReceipt"], "threshold": 0.46})
    unsigned = {"schema_id": "artflow-modular-environment-request/1", "session_id": session_id,
                "depth_path": depth.as_posix(), "depth_sha256": file_sha256(depth),
                "protected_mask_path": protected.as_posix(), "protected_mask_sha256": file_sha256(protected),
                "visual_target_path": visual.as_posix(), "visual_target_sha256": file_sha256(visual),
                "source_candidate_scene_path": foliage["candidate_scene_path"], "source_candidate_sha256": file_sha256(source),
                "comfy_capability_id": "comfy.spatial.module_zones.v1",
                "blender_capability_id": "blender.geometry_nodes.modular_environment.v1",
                "unreal_capability_id": "unreal.actors.modular_environment.v1",
                "modules": [{"module_id": "wall", "max_count": 5, "width_cm": 320, "depth_cm": 55, "height_cm": 260},
                            {"module_id": "pillar", "max_count": 5, "width_cm": 90, "depth_cm": 90, "height_cm": 360},
                            {"module_id": "gateway", "max_count": 2, "width_cm": 420, "depth_cm": 80, "height_cm": 440}],
                "placement_budget": 12, "triangle_budget": 6000, "seed": 470907, "workflow_sha256": workflow}
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"modular-environment-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return ModularEnvironmentRequest.model_validate(unsigned)


def execute_module_zones(request: ModularEnvironmentRequest, *, output_dir: Path, comfy_url: str) -> ModuleZoneReceipt:
    output_dir.mkdir(parents=True, exist_ok=True)
    depth, protected = Path(request.depth_path), Path(request.protected_mask_path)
    if file_sha256(depth) != request.depth_sha256 or file_sha256(protected) != request.protected_mask_sha256:
        raise ValueError("registered spatial input identity drifted")
    with ComfyGateway(comfy_url, timeout_seconds=20) as gateway:
        snapshot = gateway.inspect()
        required = {"WorkflowContractCheck", "ProductionConstraintCheck", "GenerationReceipt"}
        if not snapshot.reachable or not required <= set(snapshot.nodes):
            raise RuntimeError("registered ComfyUI spatial capability is unavailable")
        folder = f"ArtFlow/{request.request_id}"
        d = gateway.upload_image(depth, subfolder=folder, overwrite=True)
        p = gateway.upload_image(protected, subfolder=folder, overwrite=True)
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": f"{d.subfolder}/{d.name}"}},
            "2": {"class_type": "ImageToMask", "inputs": {"image": ["1", 0], "channel": "red"}},
            "3": {"class_type": "GrowMask", "inputs": {"mask": ["2", 0], "expand": -8, "tapered_corners": True}},
            "4": {"class_type": "ThresholdMask", "inputs": {"mask": ["3", 0], "value": 0.46}},
            "5": {"class_type": "LoadImage", "inputs": {"image": f"{p.subfolder}/{p.name}"}},
            "6": {"class_type": "ImageToMask", "inputs": {"image": ["5", 0], "channel": "red"}},
            "7": {"class_type": "GrowMask", "inputs": {"mask": ["6", 0], "expand": 18, "tapered_corners": True}},
            "8": {"class_type": "MaskComposite", "inputs": {"destination": ["4", 0], "source": ["7", 0], "x": 0, "y": 0, "operation": "subtract"}},
            "9": {"class_type": "MaskToImage", "inputs": {"mask": ["8", 0]}},
            "10": {"class_type": "SaveImage", "inputs": {"images": ["9", 0], "filename_prefix": f"ArtFlow/{request.request_id}/module-zones"}},
            "11": {"class_type": "WorkflowContractCheck", "inputs": {"contract_json": json.dumps({"outputs": ["module_zones"]}), "workflow_values_json": json.dumps({"slots": {"depth": d.name, "protected": p.name}})}},
            "12": {"class_type": "ProductionConstraintCheck", "inputs": {"width": 640, "height": 360, "batch_size": 1, "denoise": 0.0, "max_megapixels": 1.0, "max_batch_size": 1}},
            "13": {"class_type": "GenerationReceipt", "inputs": {"workflow_name": "module-zones-v1", "model_name": "deterministic-spatial-nodes", "lora_name": "none", "positive_prompt": "modular environment zones", "negative_prompt": "protected center", "seed": request.seed}},
        }
        problems = gateway.validate_workflow(workflow)
        if problems:
            raise RuntimeError("module-zone workflow failed schema validation: " + "; ".join(problems))
        queued = gateway.queue(workflow)
        history = gateway.wait(queued.prompt_id, timeout_seconds=120, poll_seconds=0.25)
        output = next(item for item in gateway.collect_outputs(history) if item.node_id == "10")
        zone = output_dir / "module-zones.png"
        gateway.download_output(output, zone)
    with Image.open(zone) as zone_image, Image.open(protected) as protected_image:
        values = list(zone_image.convert("L").getdata())
        guards = list(protected_image.convert("L").resize(zone_image.size).getdata())
    coverage = sum(value >= 128 for value in values) / len(values)
    leakage = sum(value >= 128 and guard >= 128 for value, guard in zip(values, guards, strict=True)) / max(1, sum(guard >= 128 for guard in guards))
    if not 0.02 < coverage < 0.95 or leakage > 0.01:
        raise ValueError(f"module zones failed coverage/leakage: {coverage:.4f}/{leakage:.4f}")
    payload = {"schema_id": "artflow-comfy-module-zone-receipt/1", "request_sha256": request.request_sha256,
               "capability_id": request.comfy_capability_id, "status": "succeeded",
               "comfyui_version": snapshot.comfyui_version or "unknown", "device": snapshot.device_name or "unknown",
               "provider_request_id": queued.prompt_id, "observed_node_count": len(snapshot.nodes),
               "zone_map_path": zone.name, "zone_map_sha256": file_sha256(zone),
               "zone_coverage": round(coverage, 6), "protected_leakage": round(leakage, 6),
               "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    payload["receipt_sha256"] = canonical_sha256(payload)
    receipt = ModuleZoneReceipt.model_validate(payload)
    (output_dir / "comfy-module-zone-receipt.json").write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return receipt


def execute_blender_assembly(request: ModularEnvironmentRequest, *, root: Path, output_dir: Path, blender_executable: Path) -> dict[str, object]:
    request_path = output_dir / "modular-environment-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    subprocess.run([str(blender_executable), "--background", "--factory-startup", "--python",
                    str(root / "integrations/blender/author_modular_environment.py"), "--", str(request_path), str(output_dir)],
                   cwd=root, check=True, timeout=360)
    return json.loads((output_dir / "blender-modular-environment-receipt.json").read_text(encoding="utf-8"))
