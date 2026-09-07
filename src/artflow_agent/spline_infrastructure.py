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


class SplineRouteSpec(StrictContract):
    route_id: str = Field(pattern=r"^route-[a-z0-9-]+$")
    kind: Literal["power_cable", "utility_pipe"]
    start_x_px: int = Field(ge=0, le=639)
    end_x_px: int = Field(ge=0, le=639)
    elevation_cm: int = Field(ge=40, le=500)
    diameter_cm: int = Field(ge=4, le=40)
    support_spacing_cm: int = Field(ge=150, le=600)


class SplineInfrastructureRequest(StrictContract):
    schema_id: Literal["artflow-spline-infrastructure-request/1"] = (
        "artflow-spline-infrastructure-request/1"
    )
    request_id: str = Field(pattern=r"^spline-infrastructure-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    depth_path: str
    depth_sha256: str = Field(pattern=SHA256_PATTERN)
    protected_mask_path: str
    protected_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    module_zone_path: str
    module_zone_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    route_row_px: int = Field(ge=24, le=335)
    corridor_height_px: int = Field(ge=24, le=96)
    routes: list[SplineRouteSpec] = Field(min_length=1, max_length=2)
    max_control_points_per_route: int = Field(ge=4, le=12)
    max_total_segments: int = Field(ge=6, le=32)
    seed: int = Field(ge=0, le=2**31 - 1)
    comfy_capability_id: Literal["comfy.spatial.route_corridor.v1"]
    blender_capability_id: Literal["blender.geometry_nodes.spline_infrastructure.v1"]
    unreal_capability_id: Literal["unreal.spline.infrastructure.v1"]
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> SplineInfrastructureRequest:
        if any(route.end_x_px - route.start_x_px < 72 for route in self.routes):
            raise ValueError("spline routes require a useful finite span")
        if (
            canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"}))
            != self.request_sha256
        ):
            raise ValueError("spline infrastructure request fingerprint mismatch")
        return self


class RouteCorridorReceipt(StrictContract):
    schema_id: Literal["artflow-comfy-route-corridor-receipt/1"]
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["comfy.spatial.route_corridor.v1"]
    status: Literal["succeeded"]
    comfyui_version: str
    device: str
    provider_request_id: str
    observed_node_count: int = Field(gt=0)
    corridor_path: str
    corridor_sha256: str = Field(pattern=SHA256_PATTERN)
    corridor_coverage: float = Field(gt=0.02, lt=0.95)
    protected_leakage: float = Field(ge=0, le=0.01)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> RouteCorridorReceipt:
        if (
            canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"}))
            != self.receipt_sha256
        ):
            raise ValueError("route corridor receipt fingerprint mismatch")
        return self


def _white_runs(zone: Image.Image, protected: Image.Image, row: int) -> list[tuple[int, int]]:
    allowed = [
        x
        for x in range(zone.width)
        if zone.getpixel((x, row)) >= 128 and protected.getpixel((x, row)) < 128
    ]
    if not allowed:
        return []
    runs: list[tuple[int, int]] = []
    start = previous = allowed[0]
    for value in allowed[1:]:
        if value > previous + 1:
            runs.append((start, previous))
            start = value
        previous = value
    runs.append((start, previous))
    return [item for item in runs if item[1] - item[0] >= 72]


def compile_spline_infrastructure_request(
    *, root: Path, session_id: str
) -> SplineInfrastructureRequest:
    root = root.resolve()
    depth = root / "artifacts/goal/m24-s1-scene-conditioning/depth-normalized.png"
    protected_path = root / "artifacts/goal/m34-s1-pcg-density/protected-exclusion-mask.png"
    zone_path = root / "artifacts/goal/m47-s1-modular-environment/module-zones.png"
    modular = json.loads(
        (
            root
            / "artifacts/goal/m47-s1-modular-environment/unreal-modular-environment-receipt.json"
        ).read_text(encoding="utf-8")
    )
    source = (
        root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / (modular["candidate_scene_path"].removeprefix("/Game/") + ".umap")
    )
    with Image.open(zone_path) as zone_image, Image.open(protected_path) as protected_image:
        zone = zone_image.convert("L")
        protected = protected_image.convert("L").resize(zone.size)
        rows = sorted(
            (
                (
                    sum(
                        z >= 128 and p < 128
                        for z, p in zip(
                            zone.crop((0, y, zone.width, y + 1)).getdata(),
                            protected.crop((0, y, protected.width, y + 1)).getdata(),
                            strict=True,
                        )
                    ),
                    y,
                )
                for y in range(zone.height // 4, 3 * zone.height // 4)
            ),
            reverse=True,
        )
        route_row = next(y for _, y in rows if len(_white_runs(zone, protected, y)) >= 2)
        spans = sorted(
            _white_runs(zone, protected, route_row),
            key=lambda item: item[1] - item[0],
            reverse=True,
        )[:2]
    workflow_sha256 = canonical_sha256(
        {
            "recipe": "route-corridor-v1",
            "nodes": [
                "LoadImage",
                "ImageToMask",
                "CropMask",
                "GrowMask",
                "ThresholdMask",
                "LoadImage",
                "ImageToMask",
                "CropMask",
                "GrowMask",
                "MaskComposite",
                "MaskToImage",
                "SaveImage",
                "WorkflowContractCheck",
                "ProductionConstraintCheck",
                "GenerationReceipt",
            ],
        }
    )
    routes = []
    kinds = (("power_cable", 180, 8, 280), ("utility_pipe", 90, 18, 360))
    for index, ((start, end), (kind, elevation, diameter, spacing)) in enumerate(
        zip(spans, kinds, strict=True)
    ):
        routes.append(
            {
                "route_id": f"route-{kind.replace('_', '-')}-{index + 1}",
                "kind": kind,
                "start_x_px": start,
                "end_x_px": end,
                "elevation_cm": elevation,
                "diameter_cm": diameter,
                "support_spacing_cm": spacing,
            }
        )
    unsigned = {
        "schema_id": "artflow-spline-infrastructure-request/1",
        "session_id": session_id,
        "depth_path": depth.as_posix(),
        "depth_sha256": file_sha256(depth),
        "protected_mask_path": protected_path.as_posix(),
        "protected_mask_sha256": file_sha256(protected_path),
        "module_zone_path": zone_path.as_posix(),
        "module_zone_sha256": file_sha256(zone_path),
        "source_candidate_scene_path": modular["candidate_scene_path"],
        "source_candidate_sha256": file_sha256(source),
        "route_row_px": route_row,
        "corridor_height_px": 64,
        "routes": routes,
        "max_control_points_per_route": 7,
        "max_total_segments": 16,
        "seed": 490907,
        "comfy_capability_id": "comfy.spatial.route_corridor.v1",
        "blender_capability_id": "blender.geometry_nodes.spline_infrastructure.v1",
        "unreal_capability_id": "unreal.spline.infrastructure.v1",
        "workflow_sha256": workflow_sha256,
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"spline-infrastructure-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return SplineInfrastructureRequest.model_validate(unsigned)


def execute_route_corridor(
    request: SplineInfrastructureRequest, *, output_dir: Path, comfy_url: str
) -> RouteCorridorReceipt:
    output_dir.mkdir(parents=True, exist_ok=True)
    zone = Path(request.module_zone_path)
    protected = Path(request.protected_mask_path)
    if (
        file_sha256(zone) != request.module_zone_sha256
        or file_sha256(protected) != request.protected_mask_sha256
    ):
        raise ValueError("registered route inputs changed")
    crop_y = request.route_row_px - request.corridor_height_px // 2
    with ComfyGateway(comfy_url, timeout_seconds=20) as gateway:
        snapshot = gateway.inspect()
        required = {"WorkflowContractCheck", "ProductionConstraintCheck", "GenerationReceipt"}
        if not snapshot.reachable or not required <= set(snapshot.nodes):
            raise RuntimeError("registered ComfyUI route capability is unavailable")
        folder = f"ArtFlow/{request.request_id}"
        z = gateway.upload_image(zone, subfolder=folder, overwrite=True)
        p = gateway.upload_image(protected, subfolder=folder, overwrite=True)
        workflow = {
            "1": {"class_type": "LoadImage", "inputs": {"image": f"{z.subfolder}/{z.name}"}},
            "2": {"class_type": "ImageToMask", "inputs": {"image": ["1", 0], "channel": "red"}},
            "3": {
                "class_type": "CropMask",
                "inputs": {
                    "mask": ["2", 0],
                    "x": 0,
                    "y": crop_y,
                    "width": 640,
                    "height": request.corridor_height_px,
                },
            },
            "4": {
                "class_type": "GrowMask",
                "inputs": {"mask": ["3", 0], "expand": -2, "tapered_corners": True},
            },
            "5": {"class_type": "ThresholdMask", "inputs": {"mask": ["4", 0], "value": 0.5}},
            "6": {"class_type": "LoadImage", "inputs": {"image": f"{p.subfolder}/{p.name}"}},
            "7": {"class_type": "ImageToMask", "inputs": {"image": ["6", 0], "channel": "red"}},
            "8": {
                "class_type": "CropMask",
                "inputs": {
                    "mask": ["7", 0],
                    "x": 0,
                    "y": crop_y,
                    "width": 640,
                    "height": request.corridor_height_px,
                },
            },
            "9": {
                "class_type": "GrowMask",
                "inputs": {"mask": ["8", 0], "expand": 8, "tapered_corners": True},
            },
            "10": {
                "class_type": "MaskComposite",
                "inputs": {
                    "destination": ["5", 0],
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
                    "filename_prefix": f"ArtFlow/{request.request_id}/route-corridor",
                },
            },
            "13": {
                "class_type": "WorkflowContractCheck",
                "inputs": {
                    "contract_json": json.dumps({"outputs": ["route_corridor"]}),
                    "workflow_values_json": json.dumps(
                        {"slots": {"zones": z.name, "protected": p.name}}
                    ),
                },
            },
            "14": {
                "class_type": "ProductionConstraintCheck",
                "inputs": {
                    "width": 640,
                    "height": request.corridor_height_px,
                    "batch_size": 1,
                    "denoise": 0.0,
                    "max_megapixels": 1.0,
                    "max_batch_size": 1,
                },
            },
            "15": {
                "class_type": "GenerationReceipt",
                "inputs": {
                    "workflow_name": "route-corridor-v1",
                    "model_name": "deterministic-spatial-nodes",
                    "lora_name": "none",
                    "positive_prompt": "editable utility route corridor",
                    "negative_prompt": "protected center",
                    "seed": request.seed,
                },
            },
        }
        problems = gateway.validate_workflow(workflow)
        if problems:
            raise RuntimeError("route workflow failed schema validation: " + "; ".join(problems))
        queued = gateway.queue(workflow)
        history = gateway.wait(queued.prompt_id, timeout_seconds=120, poll_seconds=0.25)
        output = next(item for item in gateway.collect_outputs(history) if item.node_id == "12")
        corridor = output_dir / "route-corridor.png"
        gateway.download_output(output, corridor)
    with Image.open(corridor) as corridor_image, Image.open(protected) as protected_image:
        values = list(corridor_image.convert("L").getdata())
        guard_crop = (
            protected_image.convert("L")
            .resize((640, 360))
            .crop((0, crop_y, 640, crop_y + request.corridor_height_px))
        )
        guards = list(guard_crop.getdata())
    coverage = sum(value >= 128 for value in values) / len(values)
    leakage = sum(
        value >= 128 and guard >= 128 for value, guard in zip(values, guards, strict=True)
    ) / max(1, sum(guard >= 128 for guard in guards))
    if not 0.02 < coverage < 0.95 or leakage > 0.01:
        raise ValueError(f"route corridor failed coverage/leakage: {coverage:.4f}/{leakage:.4f}")
    payload = {
        "schema_id": "artflow-comfy-route-corridor-receipt/1",
        "request_sha256": request.request_sha256,
        "capability_id": request.comfy_capability_id,
        "status": "succeeded",
        "comfyui_version": snapshot.comfyui_version or "unknown",
        "device": snapshot.device_name or "unknown",
        "provider_request_id": queued.prompt_id,
        "observed_node_count": len(snapshot.nodes),
        "corridor_path": corridor.name,
        "corridor_sha256": file_sha256(corridor),
        "corridor_coverage": round(coverage, 6),
        "protected_leakage": round(leakage, 6),
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    receipt = RouteCorridorReceipt.model_validate(payload)
    (output_dir / "comfy-route-corridor-receipt.json").write_text(
        receipt.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def execute_blender_spline(
    request: SplineInfrastructureRequest, *, root: Path, output_dir: Path, blender_executable: Path
) -> dict[str, object]:
    request_path = output_dir / "spline-infrastructure-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    subprocess.run(
        [
            str(blender_executable),
            "--background",
            "--factory-startup",
            "--python",
            str(root / "integrations/blender/author_spline_infrastructure.py"),
            "--",
            str(request_path),
            str(output_dir),
        ],
        cwd=root,
        check=True,
        timeout=360,
    )
    return json.loads(
        (output_dir / "blender-spline-infrastructure-receipt.json").read_text(encoding="utf-8")
    )
