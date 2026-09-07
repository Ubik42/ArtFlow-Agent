from __future__ import annotations

import hashlib
import json
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from PIL import Image, ImageStat
from pydantic import AwareDatetime, Field, model_validator

from .comfy import ComfyGateway
from .contracts.scene_delta import SHA256_PATTERN, StrictContract
from .recipes import RecipeCatalog
from .scene_lifecycle import canonical_sha256


class PixelRegion(StrictContract):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=64, le=1024)
    height: int = Field(ge=64, le=1024)


class SurfaceDetailRequest(StrictContract):
    schema_id: Literal["artflow-surface-detail-request/1"] = "artflow-surface-detail-request/1"
    request_id: str = Field(pattern=r"^surface-detail-[a-f0-9]{16}$")
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    session_sha256: str = Field(pattern=SHA256_PATTERN)
    source_level_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(
        pattern=r"^/Game/ArtFlow/Sessions/AF_[a-f0-9]{12}/Candidates/Dressing_B_[a-f0-9]{12}$"
    )
    source_render_sha256: str = Field(pattern=SHA256_PATTERN)
    source_render_region: PixelRegion
    surface_request_sha256: str = Field(pattern=SHA256_PATTERN)
    surface_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    target_object: Literal["AF_Inlay"] = "AF_Inlay"
    comfy_capability_id: Literal["comfy.surface_detail.reference_flux2_klein.v1"] = (
        "comfy.surface_detail.reference_flux2_klein.v1"
    )
    comfy_recipe_id: Literal["surface-detail-reference-v1"] = "surface-detail-reference-v1"
    blender_capability_id: Literal["blender.surface.inlay_projection_bake.v1"] = (
        "blender.surface.inlay_projection_bake.v1"
    )
    prompt: str = Field(min_length=40, max_length=1000)
    negative_prompt: str = Field(min_length=1, max_length=500)
    seed: int = Field(ge=0, le=2**63 - 1)
    denoise: float = Field(ge=0.65, le=0.85)
    resolution: Literal[512] = 512
    projection_scale: float = Field(ge=0.5, le=0.95)
    projection_offset_m: float = Field(ge=0.001, le=0.01)
    output_stem: Literal["AF_Inlay_ProjectedDetail"] = "AF_Inlay_ProjectedDetail"

    @model_validator(mode="after")
    def verify_identity(self) -> SurfaceDetailRequest:
        payload = self.model_dump(mode="json", exclude={"request_id", "request_sha256"})
        digest = canonical_sha256(payload)
        if self.request_sha256 != digest or self.request_id != f"surface-detail-{digest[:16]}":
            raise ValueError("surface-detail request fingerprint mismatch")
        return self


class DetailArtifact(StrictContract):
    kind: Literal[
        "reference_crop",
        "generated_detail",
        "projection_texture",
        "blend",
        "glb",
        "preview",
        "baked_texture",
    ]
    relative_path: str = Field(pattern=r"^[A-Za-z0-9_./-]+$")
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class ComfySurfaceDetailReceipt(StrictContract):
    schema_id: Literal["artflow-comfy-surface-detail-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["comfy.surface_detail.reference_flux2_klein.v1"]
    status: Literal["succeeded"]
    comfyui_version: str
    device: str
    observed_node_count: int = Field(gt=0)
    production_nodes: list[str] = Field(min_length=3)
    recipe_id: Literal["surface-detail-reference-v1"]
    recipe_version: Literal["1.0.0"]
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    provider_request_id: str
    image_variance: float = Field(gt=0)
    selected_detail_region: PixelRegion
    selected_pixel_coverage: float = Field(gt=0.01, le=1.0)
    artifacts: list[DetailArtifact] = Field(min_length=3, max_length=3)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> ComfySurfaceDetailReceipt:
        if {item.kind for item in self.artifacts} != {
            "reference_crop",
            "generated_detail",
            "projection_texture",
        }:
            raise ValueError("Comfy surface-detail receipt is missing an artifact")
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("Comfy surface-detail receipt fingerprint mismatch")
        return self


class BlenderSurfaceDetailReceipt(StrictContract):
    schema_id: Literal["artflow-blender-surface-detail-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    comfy_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.surface.inlay_projection_bake.v1"]
    status: Literal["succeeded"]
    blender_version: str
    target_object: Literal["AF_Inlay"]
    decal_object: Literal["AF_Inlay_ProjectedDetail"]
    vertex_count: Literal[8]
    triangle_count: Literal[12]
    uv_loop_count: Literal[24]
    material_slots: list[Literal["M_AF_ProjectedInlay"]] = Field(min_length=1, max_length=1)
    artifacts: list[DetailArtifact] = Field(min_length=4, max_length=4)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderSurfaceDetailReceipt:
        if {item.kind for item in self.artifacts} != {"blend", "glb", "preview", "baked_texture"}:
            raise ValueError("Blender surface-detail receipt is missing an artifact")
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("Blender surface-detail receipt fingerprint mismatch")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_surface_detail_request(
    *, session_id: str, session_sha256: str, source_level_sha256: str,
    surface_request_path: Path, surface_receipt_path: Path, source_blend_path: Path,
    dressing_return_path: Path, source_render_path: Path,
) -> SurfaceDetailRequest:
    surface_request = json.loads(surface_request_path.read_text(encoding="utf-8"))
    surface_receipt = json.loads(surface_receipt_path.read_text(encoding="utf-8"))
    dressing_return = json.loads(dressing_return_path.read_text(encoding="utf-8"))
    blend = next(item for item in surface_receipt["artifacts"] if item["kind"] == "blend")
    if surface_receipt["request_sha256"] != surface_request["request_sha256"]:
        raise ValueError("surface request and receipt do not match")
    if file_sha256(source_blend_path) != blend["sha256"]:
        raise ValueError("surface blend identity drifted")
    if dressing_return.get("capture_status") != "completed":
        raise ValueError("dressing candidate capture is incomplete")
    if file_sha256(source_render_path) != dressing_return.get("screenshot_sha256"):
        raise ValueError("dressing candidate render identity drifted")
    unsigned = {
        "schema_id": "artflow-surface-detail-request/1",
        "session_id": session_id,
        "session_sha256": session_sha256,
        "source_level_sha256": source_level_sha256,
        "source_candidate_scene_path": dressing_return["candidate_scene_path"],
        "source_render_sha256": file_sha256(source_render_path),
        "source_render_region": {"x": 500, "y": 56, "width": 320, "height": 320},
        "surface_request_sha256": surface_request["request_sha256"],
        "surface_receipt_sha256": surface_receipt["receipt_sha256"],
        "source_blend_sha256": file_sha256(source_blend_path),
        "target_object": "AF_Inlay",
        "comfy_capability_id": "comfy.surface_detail.reference_flux2_klein.v1",
        "comfy_recipe_id": "surface-detail-reference-v1",
        "blender_capability_id": "blender.surface.inlay_projection_bake.v1",
        "prompt": (
            "orthographic square ancient bronze-and-stone shrine inlay surface filling the frame, "
            "carved concentric sun glyph with restrained turquoise oxidation, physically plausible "
            "game material detail, frontal flat albedo, preserve the source warm stone palette"
        ),
        "negative_prompt": "scene, camera, perspective, horizon, characters, text, logo, watermark, frame, cast shadow",
        "seed": 300907,
        "denoise": 0.82,
        "resolution": 512,
        "projection_scale": 0.86,
        "projection_offset_m": 0.003,
        "output_stem": "AF_Inlay_ProjectedDetail",
    }
    digest = canonical_sha256(unsigned)
    return SurfaceDetailRequest.model_validate(
        {**unsigned, "request_id": f"surface-detail-{digest[:16]}", "request_sha256": digest}
    )


def _artifact(kind: str, path: Path, root: Path) -> dict[str, object]:
    return {
        "kind": kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": file_sha256(path),
        "size_bytes": path.stat().st_size,
    }


def _finalize_comfy_receipt(
    request: SurfaceDetailRequest,
    output_dir: Path,
    facts: dict[str, object],
) -> ComfySurfaceDetailReceipt:
    generated_path = output_dir / "AF_Inlay_GeneratedDetail.png"
    reference_path = output_dir / "AF_Inlay_SceneReference.png"
    with Image.open(generated_path) as generated_source:
        generated = generated_source.convert("RGB")
        if generated.size != (request.resolution, request.resolution):
            raise ValueError("generated surface detail has unexpected dimensions")
        hsv = generated.convert("HSV")
        search_left = int(generated.width * 0.15)
        search_right = int(generated.width * 0.8)
        search_top = int(generated.height * 0.25)
        search_bottom = int(generated.height * 0.96)
        pixels = hsv.load()
        selected = [
            (x, y)
            for y in range(search_top, search_bottom)
            for x in range(search_left, search_right)
            if 70 <= pixels[x, y][0] <= 140
            and pixels[x, y][1] > 70
            and pixels[x, y][2] > 50
        ]
        search_area = (search_right - search_left) * (search_bottom - search_top)
        coverage = len(selected) / search_area
        if coverage <= 0.01:
            raise ValueError("generated detail has no bounded oxidized-inlay region")
        pad = 6
        left = max(0, min(x for x, _ in selected) - pad)
        top = max(0, min(y for _, y in selected) - pad)
        right = min(generated.width, max(x for x, _ in selected) + pad + 1)
        bottom = min(generated.height, max(y for _, y in selected) + pad + 1)
        projection = generated.crop((left, top, right, bottom)).resize(
            (request.resolution, request.resolution), Image.Resampling.LANCZOS
        )
    projection_path = output_dir / "AF_Inlay_ProjectionTexture.png"
    projection.save(projection_path)
    variance = round(sum(ImageStat.Stat(projection).var) / 3.0, 3)
    facts["image_variance"] = variance
    facts["selected_detail_region"] = {
        "x": left,
        "y": top,
        "width": right - left,
        "height": bottom - top,
    }
    facts["selected_pixel_coverage"] = round(coverage, 6)
    facts["artifacts"] = [
        _artifact("reference_crop", reference_path, output_dir),
        _artifact("generated_detail", generated_path, output_dir),
        _artifact("projection_texture", projection_path, output_dir),
    ]
    facts["receipt_sha256"] = canonical_sha256(facts)
    receipt = ComfySurfaceDetailReceipt.model_validate(facts)
    (output_dir / "comfy-surface-detail-receipt.json").write_text(
        receipt.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return receipt


def reconcile_existing_comfy_surface_detail(
    request: SurfaceDetailRequest, output_dir: Path
) -> ComfySurfaceDetailReceipt:
    raw = json.loads((output_dir / "comfy-surface-detail-receipt.json").read_text(encoding="utf-8"))
    if raw.get("request_sha256") != request.request_sha256:
        raise ValueError("existing Comfy receipt belongs to another surface-detail request")
    for name, kind in (
        ("AF_Inlay_SceneReference.png", "reference_crop"),
        ("AF_Inlay_GeneratedDetail.png", "generated_detail"),
    ):
        path = output_dir / name
        prior = next((item for item in raw.get("artifacts", []) if item.get("kind") == kind), None)
        if prior is None or file_sha256(path) != prior.get("sha256"):
            raise ValueError(f"existing Comfy artifact identity mismatch: {kind}")
    facts = {
        key: value
        for key, value in raw.items()
        if key
        not in {
            "image_variance",
            "selected_detail_region",
            "selected_pixel_coverage",
            "artifacts",
            "receipt_sha256",
        }
    }
    return _finalize_comfy_receipt(request, output_dir, facts)


def execute_comfy_surface_detail(
    request: SurfaceDetailRequest, *, source_render_path: Path, output_dir: Path,
    comfy_url: str = "http://127.0.0.1:8190", timeout_seconds: int = 600,
) -> ComfySurfaceDetailReceipt:
    output_dir.mkdir(parents=True, exist_ok=True)
    if file_sha256(source_render_path) != request.source_render_sha256:
        raise ValueError("surface-detail render identity mismatch")
    with Image.open(source_render_path) as source:
        region = request.source_render_region
        if region.x + region.width > source.width or region.y + region.height > source.height:
            raise ValueError("surface-detail region escaped the source render")
        crop = source.convert("RGB").crop(
            (region.x, region.y, region.x + region.width, region.y + region.height)
        ).resize((request.resolution, request.resolution), Image.Resampling.LANCZOS)
    crop_path = output_dir / "AF_Inlay_SceneReference.png"
    crop.save(crop_path)
    recipe = RecipeCatalog.bundled().get(request.comfy_recipe_id)
    started = time.perf_counter()
    with ComfyGateway(comfy_url, timeout_seconds=30) as gateway:
        snapshot = gateway.inspect()
        problems = recipe.validate_environment(snapshot)
        if problems:
            raise RuntimeError("ComfyUI surface-detail capability unavailable: " + "; ".join(problems))
        subfolder = f"ArtFlow/{request.request_id}"
        uploaded = gateway.upload_image(crop_path, subfolder=subfolder, overwrite=True)
        source_identity = "/".join(part for part in (uploaded.subfolder, uploaded.name) if part)
        contract = json.dumps(
            {
                "required_slots": ["source_image", "target_object"],
                "parameter_ranges": {"denoise": {"min": 0.65, "max": 0.85}, "width": {"min": 512, "max": 1024}, "height": {"min": 512, "max": 1024}},
            },
            sort_keys=True,
        )
        values = json.dumps(
            {
                "slots": {"source_image": source_identity, "target_object": request.target_object},
                "parameters": {"denoise": request.denoise, "width": request.resolution, "height": request.resolution},
            },
            sort_keys=True,
        )
        workflow = recipe.instantiate(
            {
                "source_image": source_identity,
                "positive_prompt": request.prompt,
                "negative_prompt": request.negative_prompt,
                "seed": request.seed,
                "denoise": request.denoise,
                "width": request.resolution,
                "height": request.resolution,
                "filename_prefix": f"ArtFlow/{request.request_id}/detail",
                "contract_json": contract,
                "workflow_values_json": values,
            }
        )
        schema_problems = gateway.validate_workflow(workflow)
        if schema_problems:
            raise RuntimeError("live surface-detail workflow rejected: " + "; ".join(schema_problems))
        job = gateway.queue(workflow, client_id=request.request_id)
        history = gateway.wait(job.prompt_id, timeout_seconds=timeout_seconds)
        outputs = [item for item in gateway.collect_outputs(history) if item.node_id == "18"]
        if len(outputs) != 1:
            raise RuntimeError("surface-detail workflow did not return exactly one image")
        generated_path = output_dir / "AF_Inlay_GeneratedDetail.png"
        gateway.download_output(outputs[0], generated_path)
    facts = {
        "schema_id": "artflow-comfy-surface-detail-receipt/1",
        "request_id": request.request_id,
        "request_sha256": request.request_sha256,
        "capability_id": request.comfy_capability_id,
        "status": "succeeded",
        "comfyui_version": snapshot.comfyui_version or "unknown",
        "device": snapshot.device_name or "unknown",
        "observed_node_count": len(snapshot.nodes),
        "production_nodes": sorted(node for node in snapshot.nodes if node in {"ProductionConstraintCheck", "WorkflowContractCheck", "GenerationReceipt"}),
        "recipe_id": recipe.definition.recipe_id,
        "recipe_version": recipe.definition.version,
        "workflow_sha256": canonical_sha256(workflow),
        "provider_request_id": job.prompt_id,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    return _finalize_comfy_receipt(request, output_dir, facts)


def verify_surface_detail_artifacts(
    request: SurfaceDetailRequest, comfy_receipt: ComfySurfaceDetailReceipt,
    blender_receipt: BlenderSurfaceDetailReceipt, output_dir: Path,
) -> None:
    if comfy_receipt.request_sha256 != request.request_sha256:
        raise ValueError("Comfy surface detail belongs to another request")
    if blender_receipt.request_sha256 != request.request_sha256:
        raise ValueError("Blender surface detail belongs to another request")
    if blender_receipt.comfy_receipt_sha256 != comfy_receipt.receipt_sha256:
        raise ValueError("Blender projection references another Comfy receipt")
    for artifact in [*comfy_receipt.artifacts, *blender_receipt.artifacts]:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir.resolve() not in path.parents or file_sha256(path) != artifact.sha256:
            raise ValueError(f"surface-detail artifact identity mismatch: {artifact.kind}")


def execute_blender_surface_detail(
    request: SurfaceDetailRequest, comfy_receipt: ComfySurfaceDetailReceipt, *,
    project_root: Path, source_blend_path: Path, output_dir: Path,
    blender_executable: Path, timeout_seconds: int = 300,
) -> BlenderSurfaceDetailReceipt:
    if project_root.resolve() not in output_dir.resolve().parents:
        raise ValueError("surface-detail output must stay inside the project")
    if file_sha256(source_blend_path) != request.source_blend_sha256:
        raise ValueError("surface-detail source blend identity mismatch")
    request_path = output_dir / "surface-detail-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    script = project_root / "integrations/blender/project_surface_detail.py"
    subprocess.run(
        [str(blender_executable), "--background", "--factory-startup", "--python", str(script), "--", str(request_path), str(output_dir / "comfy-surface-detail-receipt.json"), str(output_dir), str(source_blend_path)],
        cwd=project_root,
        check=True,
        timeout=timeout_seconds,
    )
    receipt_path = output_dir / "blender-surface-detail-receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError("Blender exited without a surface-detail receipt")
    receipt = BlenderSurfaceDetailReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    verify_surface_detail_artifacts(request, comfy_receipt, receipt, output_dir)
    return receipt
