from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .agent_runtime import AgentEventStore, AgentRuntimeError
from .blender_set_dressing import (
    BlenderSetDressingReceipt,
    BlenderSetDressingRequest,
    verify_set_dressing,
)
from .blender_surface import BlenderSurfaceRequest
from .camera_move import BlenderCameraMoveReceipt, CameraMoveRequest
from .cloth_banner import BannerTextureReceipt, ClothBannerRequest
from .damage_variant import DamageFieldReceipt, DamageVariantRequest
from .foliage_kit import FoliageKitRequest
from .lookdev_handoff import SceneLookdevRequest
from .material_variation import (
    BlenderMaterialVariationReceipt,
    MaterialVariationRequest,
    verify_material_variation,
)
from .mechanism_rig import MechanismRigRequest
from .mechanism_shot import MechanismShotRequest
from .modular_environment import ModularEnvironmentRequest
from .pcg_density import PcgDensityReceipt, PcgDensityRequest
from .procedural_kit import ProceduralKitReceipt, ProceduralKitRequest, verify_procedural_kit
from .scene_dcc_work import SceneDccWorkDefinition, SceneDccWorkProgressRequest
from .shot_package import ShotPackageRequest
from .simulation_cache import BlenderSimulationCacheReceipt, SimulationCacheRequest
from .spline_infrastructure import SplineInfrastructureRequest
from .surface_detail import (
    BlenderSurfaceDetailReceipt,
    ComfySurfaceDetailReceipt,
    SurfaceDetailRequest,
    verify_surface_detail_artifacts,
)

WORKER_ID = "artflow-local-blender-worker-v1"


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load_receipt(path: Path, *, expected_sha256: str) -> dict[str, object]:
    receipt = json.loads(path.read_text(encoding="utf-8"))
    recorded = receipt.get("receipt_sha256")
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    if recorded != expected_sha256 or _canonical_sha256(payload) != expected_sha256:
        raise ValueError(f"DCC receipt identity changed: {path.name}")
    return receipt


def _verify_artifacts(root: Path, receipt: dict[str, object]) -> None:
    artifacts = receipt.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise TypeError("DCC receipt artifacts must be a list")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise TypeError("DCC artifact entry must be an object")
        path = (root / str(artifact["relative_path"])).resolve()
        if root.resolve() not in path.parents:
            raise ValueError("DCC artifact escaped its registered root")
        if not path.is_file() or _file_sha256(path) != artifact["sha256"]:
            raise ValueError(f"DCC artifact identity changed: {path.name}")


def _reconcile_selected_route(project_root: Path, work: SceneDccWorkDefinition) -> str:
    decision = work.route_decision
    if decision is None:
        raise ValueError("selected route reconciliation requires a route decision")
    if decision.selected_route_id == "cloth_banner":
        root = project_root / "artifacts/goal/m57-s1-cloth-banner"
        request = ClothBannerRequest.model_validate_json(
            (root / "cloth-banner-request.json").read_text(encoding="utf-8")
        )
        comfy = BannerTextureReceipt.model_validate_json(
            (root / "comfy-banner-texture-receipt.json").read_text(encoding="utf-8")
        )
        blender = _load_receipt(
            root / "blender-cloth-banner-receipt.json",
            expected_sha256=str(work.blender_cloth_banner_receipt_sha256),
        )
        unreal = _load_receipt(
            root / "unreal-cloth-banner-receipt.json",
            expected_sha256=str(work.unreal_cloth_banner_receipt_sha256),
        )
        _verify_artifacts(root, blender)
        artifacts = {str(item["kind"]): item for item in blender["artifacts"]}
        if (
            request.request_sha256 != work.cloth_banner_request_sha256
            or comfy.receipt_sha256 != work.comfy_banner_texture_receipt_sha256
            or comfy.texture_sha256 != work.banner_texture_sha256
            or _file_sha256(root / comfy.texture_path) != work.banner_texture_sha256
            or blender.get("request_sha256") != request.request_sha256
            or blender.get("comfy_receipt_sha256") != comfy.receipt_sha256
            or artifacts["blend"]["sha256"] != work.cloth_banner_blend_sha256
            or artifacts["glb"]["sha256"] != work.cloth_banner_glb_sha256
            or artifacts["manifest"]["sha256"] != work.cloth_banner_manifest_sha256
            or unreal.get("blender_receipt_sha256") != blender.get("receipt_sha256")
            or unreal.get("candidate_scene_path") != work.candidate_scene_path
            or unreal.get("status") != "reconciled"
            or unreal.get("created_actor_count") != 0
            or unreal.get("updated_actor_count") != 0
            or unreal.get("duplicate_asset_count") != 0
            or unreal.get("source_candidate_sha256_before")
            != unreal.get("source_candidate_sha256_after")
            or _file_sha256(root / str(unreal["screenshot_path"]))
            != work.cloth_banner_unreal_preview_sha256
        ):
            raise ValueError("selected cloth-banner route changed after dispatch")
    elif decision.selected_route_id == "damage_variant":
        root = project_root / "artifacts/goal/m55-s1-damage-variant"
        request = DamageVariantRequest.model_validate_json(
            (root / "damage-variant-request.json").read_text(encoding="utf-8")
        )
        comfy = DamageFieldReceipt.model_validate_json(
            (root / "comfy-damage-field-receipt.json").read_text(encoding="utf-8")
        )
        blender = _load_receipt(
            root / "blender-damage-variant-receipt.json",
            expected_sha256=str(work.blender_damage_variant_receipt_sha256),
        )
        unreal = _load_receipt(
            root / "unreal-damage-variant-receipt.json",
            expected_sha256=str(work.unreal_damage_variant_receipt_sha256),
        )
        _verify_artifacts(root, blender)
        artifacts = {str(item["kind"]): item for item in blender["artifacts"]}
        if (
            request.request_sha256 != work.damage_variant_request_sha256
            or comfy.receipt_sha256 != work.comfy_damage_field_receipt_sha256
            or comfy.field_sha256 != work.damage_field_sha256
            or _file_sha256(root / comfy.field_path) != work.damage_field_sha256
            or artifacts["glb"]["sha256"] != work.damage_glb_sha256
            or artifacts["manifest"]["sha256"] != work.damage_manifest_sha256
            or unreal.get("blender_receipt_sha256") != blender.get("receipt_sha256")
            or unreal.get("candidate_scene_path") != work.candidate_scene_path
            or unreal.get("status") != "reconciled"
        ):
            raise ValueError("selected damage route changed after dispatch")
    else:
        root = project_root / "artifacts/goal/m53-s1-mechanism-shot"
        request = MechanismShotRequest.model_validate_json(
            (root / "mechanism-shot-request.json").read_text(encoding="utf-8")
        )
        unreal = _load_receipt(
            root / "unreal-mechanism-shot-receipt.json",
            expected_sha256=str(work.unreal_mechanism_shot_receipt_sha256),
        )
        previews = unreal.get("preview_sha256s", {})
        if (
            request.request_sha256 != work.mechanism_shot_request_sha256
            or unreal.get("request_sha256") != request.request_sha256
            or unreal.get("candidate_scene_path") != work.candidate_scene_path
            or unreal.get("sequence_asset_path") != work.mechanism_shot_sequence_path
            or previews.get("closed_start") != work.mechanism_shot_closed_start_sha256
            or previews.get("open") != work.mechanism_shot_open_sha256
            or previews.get("closed_end") != work.mechanism_shot_closed_end_sha256
            or unreal.get("status") != "reconciled"
        ):
            raise ValueError("selected mechanism-shot route changed after dispatch")
        for label, expected in previews.items():
            if _file_sha256(root / str(unreal["preview_paths"][label])) != expected:
                raise ValueError(f"selected mechanism-shot preview changed: {label}")
    return work.unreal_return_receipt_sha256


def reconcile_registered_chain(project_root: Path, work: SceneDccWorkDefinition) -> str:
    if work.route_decision is not None:
        return _reconcile_selected_route(project_root, work)
    roots = {
        "model": project_root / "artifacts/goal/m23-s1-blender-modeling",
        "pbr": project_root / "artifacts/goal/m23-s2-blender-pbr",
        "layout": project_root / "artifacts/goal/m23-s4-geometry-layout",
        "shot": project_root / "artifacts/goal/m23-s5-camera-light",
        "conditioning": project_root / "artifacts/goal/m24-s1-scene-conditioning",
        "lookdev": project_root / "artifacts/goal/m24-s2-scene-lookdev",
        "surface": project_root / "artifacts/goal/m26-s1-surface-bake",
        "dressing": project_root / "artifacts/goal/m28-s1-set-dressing",
        "detail": project_root / "artifacts/goal/m30-s1-surface-detail",
        "kit": project_root / "artifacts/goal/m32-s1-procedural-kit",
        "density": project_root / "artifacts/goal/m34-s1-pcg-density",
        "shot_package": project_root / "artifacts/goal/m36-s1-shot-package",
        "camera_move": project_root / "artifacts/goal/m38-s1-camera-move",
        "material_variation": project_root / "artifacts/goal/m40-s1-material-variation",
        "terrain": project_root / "artifacts/goal/m42-s1-terrain-biome",
        "simulation_cache": project_root / "artifacts/goal/m43-s1-simulation-cache",
        "foliage": project_root / "artifacts/goal/m45-s1-foliage-kit",
        "modular": project_root / "artifacts/goal/m47-s1-modular-environment",
        "spline": project_root / "artifacts/goal/m49-s1-spline-infrastructure",
        "mechanism": project_root / "artifacts/goal/m51-s1-mechanism-rig",
        "mechanism_shot": project_root / "artifacts/goal/m53-s1-mechanism-shot",
        "damage": project_root / "artifacts/goal/m55-s1-damage-variant",
        "cloth_banner": project_root / "artifacts/goal/m57-s1-cloth-banner",
    }
    model_request = json.loads(
        (roots["model"] / "modeling-request.json").read_text(encoding="utf-8")
    )
    pbr_request = json.loads(
        (roots["pbr"] / "pbr-assembly-request.json").read_text(encoding="utf-8")
    )
    if model_request["request_sha256"] != work.modeling_request_sha256:
        raise ValueError("registered modeling request changed")
    if pbr_request["request_sha256"] != work.pbr_request_sha256:
        raise ValueError("registered PBR request changed")

    if work.layout_request_sha256 is not None:
        layout_request = json.loads(
            (roots["layout"] / "layout-request.json").read_text(encoding="utf-8")
        )
        if layout_request["request_sha256"] != work.layout_request_sha256:
            raise ValueError("registered Geometry Nodes request changed")
        layout_receipt = _load_receipt(
            roots["layout"] / "layout-receipt.json",
            expected_sha256=str(work.layout_receipt_sha256),
        )
        _verify_artifacts(roots["layout"], layout_receipt)

    if work.shot_request_sha256 is not None:
        shot_request = json.loads((roots["shot"] / "shot-request.json").read_text(encoding="utf-8"))
        if shot_request["request_sha256"] != work.shot_request_sha256:
            raise ValueError("registered camera-light request changed")
        shot_receipt = _load_receipt(
            roots["shot"] / "shot-receipt.json",
            expected_sha256=str(work.shot_receipt_sha256),
        )
        _verify_artifacts(roots["shot"], shot_receipt)
        unreal_receipt = _load_receipt(
            roots["shot"] / "unreal-shot-return-receipt.json",
            expected_sha256=str(work.unreal_shot_return_receipt_sha256),
        )
        if (
            work.lookdev_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal shot candidate changed")
        screenshot = roots["shot"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal shot screenshot identity changed")

    if work.lookdev_request_sha256 is not None:
        lookdev_request = SceneLookdevRequest.model_validate_json(
            (roots["lookdev"] / "lookdev-request.json").read_text(encoding="utf-8")
        )
        if lookdev_request.request_sha256 != work.lookdev_request_sha256:
            raise ValueError("registered scene-conditioned lookdev request changed")
        if lookdev_request.accepted_artifact_sha256 != work.accepted_visual_target_sha256:
            raise ValueError("registered visual target identity changed")
        target = roots["conditioning"] / "depth-guided-candidate.png"
        if _file_sha256(target) != work.accepted_visual_target_sha256:
            raise ValueError("accepted visual target bytes changed")
        lookdev_receipt = _load_receipt(
            roots["lookdev"] / "lookdev-receipt.json",
            expected_sha256=str(work.lookdev_receipt_sha256),
        )
        _verify_artifacts(roots["lookdev"], lookdev_receipt)
        unreal_receipt = _load_receipt(
            roots["lookdev"] / "unreal-lookdev-return-receipt.json",
            expected_sha256=str(work.unreal_lookdev_return_receipt_sha256),
        )
        if (
            work.surface_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal lookdev candidate changed")
        shot_return = json.loads(
            (roots["shot"] / "unreal-shot-return-receipt.json").read_text(encoding="utf-8")
        )
        if unreal_receipt.get("source_candidate_scene_path") != shot_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("Unreal lookdev candidate no longer derives from the registered shot")
        screenshot = roots["lookdev"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal lookdev screenshot identity changed")

    if work.surface_request_sha256 is not None:
        surface_request = BlenderSurfaceRequest.model_validate_json(
            (roots["surface"] / "surface-request.json").read_text(encoding="utf-8")
        )
        if surface_request.request_sha256 != work.surface_request_sha256:
            raise ValueError("registered surface request changed")
        surface_receipt = _load_receipt(
            roots["surface"] / "surface-receipt.json",
            expected_sha256=str(work.surface_receipt_sha256),
        )
        _verify_artifacts(roots["surface"], surface_receipt)
        unreal_receipt = _load_receipt(
            roots["surface"] / "unreal-surface-return-receipt.json",
            expected_sha256=str(work.unreal_surface_return_receipt_sha256),
        )
        if (
            work.set_dressing_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal surface candidate changed")
        lookdev_return = json.loads(
            (roots["lookdev"] / "unreal-lookdev-return-receipt.json").read_text(encoding="utf-8")
        )
        if unreal_receipt.get("source_candidate_scene_path") != lookdev_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("Unreal surface candidate no longer derives from lookdev")
        screenshot = roots["surface"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal surface screenshot identity changed")

    if work.set_dressing_request_sha256 is not None:
        request = BlenderSetDressingRequest.model_validate_json(
            (roots["dressing"] / "set-dressing-request.json").read_text(encoding="utf-8")
        )
        receipt = BlenderSetDressingReceipt.model_validate_json(
            (roots["dressing"] / "set-dressing-receipt.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.set_dressing_request_sha256:
            raise ValueError("registered set-dressing request changed")
        if receipt.receipt_sha256 != work.set_dressing_receipt_sha256:
            raise ValueError("registered set-dressing receipt changed")
        verify_set_dressing(request, receipt, roots["dressing"])
        manifest_artifact = next(
            item for item in receipt.artifacts if item.kind == "transform_manifest"
        )
        if manifest_artifact.sha256 != work.set_dressing_manifest_sha256:
            raise ValueError("registered transform manifest changed")
        unreal_receipt = _load_receipt(
            roots["dressing"] / "unreal-set-dressing-return-receipt.json",
            expected_sha256=str(work.unreal_set_dressing_return_receipt_sha256),
        )
        if (
            work.surface_detail_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal set-dressing candidate changed")
        surface_return = json.loads(
            (roots["surface"] / "unreal-surface-return-receipt.json").read_text(encoding="utf-8")
        )
        if unreal_receipt.get("source_candidate_scene_path") != surface_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("Unreal set-dressing candidate no longer derives from surface")
        screenshot = roots["dressing"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal set-dressing screenshot identity changed")

    if work.surface_detail_request_sha256 is not None:
        request = SurfaceDetailRequest.model_validate_json(
            (roots["detail"] / "surface-detail-request.json").read_text(encoding="utf-8")
        )
        comfy_receipt = ComfySurfaceDetailReceipt.model_validate_json(
            (roots["detail"] / "comfy-surface-detail-receipt.json").read_text(encoding="utf-8")
        )
        blender_receipt = BlenderSurfaceDetailReceipt.model_validate_json(
            (roots["detail"] / "blender-surface-detail-receipt.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.surface_detail_request_sha256:
            raise ValueError("registered surface-detail request changed")
        if comfy_receipt.receipt_sha256 != work.comfy_surface_detail_receipt_sha256:
            raise ValueError("registered Comfy surface-detail receipt changed")
        if blender_receipt.receipt_sha256 != work.blender_surface_detail_receipt_sha256:
            raise ValueError("registered Blender surface-detail receipt changed")
        verify_surface_detail_artifacts(request, comfy_receipt, blender_receipt, roots["detail"])
        unreal_receipt = _load_receipt(
            roots["detail"] / "unreal-surface-detail-return-receipt.json",
            expected_sha256=str(work.unreal_surface_detail_return_receipt_sha256),
        )
        if (
            work.procedural_kit_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal surface-detail candidate changed")
        dressing_return = json.loads(
            (roots["dressing"] / "unreal-set-dressing-return-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if unreal_receipt.get("source_candidate_scene_path") != dressing_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("surface-detail candidate no longer derives from set dressing")
        screenshot = roots["detail"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal surface-detail screenshot identity changed")

    if work.procedural_kit_request_sha256 is not None:
        request = ProceduralKitRequest.model_validate_json(
            (roots["kit"] / "procedural-kit-request.json").read_text(encoding="utf-8")
        )
        receipt = ProceduralKitReceipt.model_validate_json(
            (roots["kit"] / "procedural-kit-receipt.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.procedural_kit_request_sha256:
            raise ValueError("registered procedural-kit request changed")
        if receipt.receipt_sha256 != work.procedural_kit_receipt_sha256:
            raise ValueError("registered procedural-kit receipt changed")
        verify_procedural_kit(request, receipt, roots["kit"])
        manifest = next(item for item in receipt.artifacts if item.kind == "manifest")
        if manifest.sha256 != work.procedural_kit_manifest_sha256:
            raise ValueError("registered procedural-kit manifest changed")
        unreal_receipt = _load_receipt(
            roots["kit"] / "unreal-procedural-kit-return-receipt.json",
            expected_sha256=str(work.unreal_procedural_kit_return_receipt_sha256),
        )
        if (
            work.pcg_density_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal procedural-kit candidate changed")
        detail_return = json.loads(
            (roots["detail"] / "unreal-surface-detail-return-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if unreal_receipt.get("source_candidate_scene_path") != detail_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("procedural-kit candidate no longer derives from surface detail")
        screenshot = roots["kit"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal procedural-kit screenshot identity changed")

    if work.pcg_density_request_sha256 is not None:
        request = PcgDensityRequest.model_validate_json(
            (roots["density"] / "pcg-density-request.json").read_text(encoding="utf-8")
        )
        receipt = PcgDensityReceipt.model_validate_json(
            (roots["density"] / "pcg-density-receipt.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.pcg_density_request_sha256:
            raise ValueError("registered PCG density request changed")
        if receipt.receipt_sha256 != work.pcg_density_receipt_sha256:
            raise ValueError("registered PCG density receipt changed")
        spatial_path = roots["density"] / receipt.spatial_manifest_path
        if _file_sha256(spatial_path) != work.pcg_density_spatial_manifest_sha256:
            raise ValueError("registered PCG density spatial manifest changed")
        unreal_receipt = _load_receipt(
            roots["density"] / "unreal-native-pcg-density-receipt.json",
            expected_sha256=str(work.unreal_native_pcg_density_receipt_sha256),
        )
        if unreal_receipt.get("native_pcg_graph_path") != work.native_pcg_graph_path:
            raise ValueError("registered native PCG graph changed")
        if (
            work.shot_package_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal native PCG candidate changed")
        kit_return = json.loads(
            (roots["kit"] / "unreal-procedural-kit-return-receipt.json").read_text(encoding="utf-8")
        )
        if unreal_receipt.get("source_candidate_scene_path") != kit_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("native PCG candidate no longer derives from procedural kit")
        if unreal_receipt.get("generated_instance_count") != 12:
            raise ValueError("native PCG instance count changed")
        screenshot = roots["density"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal native PCG screenshot identity changed")

    if work.shot_package_request_sha256 is not None:
        request = ShotPackageRequest.model_validate_json(
            (roots["shot_package"] / "shot-package-request.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.shot_package_request_sha256:
            raise ValueError("registered shot-package request changed")
        unreal_receipt = _load_receipt(
            roots["shot_package"] / "unreal-shot-package-receipt.json",
            expected_sha256=str(work.unreal_shot_package_receipt_sha256),
        )
        if unreal_receipt.get("request_sha256") != request.request_sha256:
            raise ValueError("Unreal shot package references another request")
        if (
            work.material_variation_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal shot-package candidate changed")
        if unreal_receipt.get("sequence_asset_path") != work.level_sequence_path:
            raise ValueError("registered Level Sequence changed")
        density_return = json.loads(
            (roots["density"] / "unreal-native-pcg-density-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if unreal_receipt.get("source_candidate_scene_path") != density_return.get(
            "candidate_scene_path"
        ):
            raise ValueError("shot package no longer derives from native PCG")
        if {
            unreal_receipt.get("source_candidate_sha256_before"),
            unreal_receipt.get("source_candidate_sha256_after"),
        } != {request.source_candidate_sha256}:
            raise ValueError("shot package changed its source PCG candidate")
        expected_counts = {
            "sequence_binding_count": 4,
            "camera_binding_count": 1,
            "light_binding_count": 3,
            "camera_cut_track_count": 1,
        }
        if any(unreal_receipt.get(key) != value for key, value in expected_counts.items()):
            raise ValueError("shot package binding topology changed")
        screenshot = roots["shot_package"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal shot-package screenshot identity changed")

    if work.camera_move_request_sha256 is not None:
        request = CameraMoveRequest.model_validate_json(
            (roots["camera_move"] / "camera-move-request.json").read_text(encoding="utf-8")
        )
        blender_receipt = BlenderCameraMoveReceipt.model_validate_json(
            (roots["camera_move"] / "blender-camera-move-receipt.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.camera_move_request_sha256:
            raise ValueError("registered camera-move request changed")
        if blender_receipt.receipt_sha256 != work.blender_camera_move_receipt_sha256:
            raise ValueError("registered Blender camera-move receipt changed")
        for artifact in blender_receipt.artifacts:
            path = (roots["camera_move"] / artifact.relative_path).resolve()
            if roots["camera_move"].resolve() not in path.parents:
                raise ValueError("camera-move artifact escaped its registered root")
            if not path.is_file() or _file_sha256(path) != artifact.sha256:
                raise ValueError("Blender camera-move artifact identity changed")
        unreal_receipt = _load_receipt(
            roots["camera_move"] / "unreal-camera-move-receipt.json",
            expected_sha256=str(work.unreal_camera_move_receipt_sha256),
        )
        if unreal_receipt.get("request_sha256") != request.request_sha256:
            raise ValueError("Unreal camera move references another request")
        if unreal_receipt.get("blender_receipt_sha256") != blender_receipt.receipt_sha256:
            raise ValueError("Unreal camera move references another Blender receipt")
        if unreal_receipt.get("source_sequence_path") != work.level_sequence_path:
            raise ValueError("camera move source Level Sequence changed")
        shot_package_receipt = json.loads(
            (roots["shot_package"] / "unreal-shot-package-receipt.json").read_text(encoding="utf-8")
        )
        if unreal_receipt.get("source_candidate_scene_path") != shot_package_receipt.get(
            "candidate_scene_path"
        ):
            raise ValueError("camera move source candidate changed")
        if unreal_receipt.get("sequence_asset_path") != work.camera_move_sequence_path:
            raise ValueError("camera-move Level Sequence changed")
        if {
            unreal_receipt.get("source_sequence_sha256_before"),
            unreal_receipt.get("source_sequence_sha256_after"),
        } != {request.source_sequence_sha256}:
            raise ValueError("camera move changed its source Level Sequence")
        if {
            unreal_receipt.get("source_candidate_sha256_before"),
            unreal_receipt.get("source_candidate_sha256_after"),
        } != {request.source_candidate_sha256}:
            raise ValueError("camera move changed its source candidate")
        if (
            unreal_receipt.get("transform_track_count") != 1
            or unreal_receipt.get("transform_section_count") != 1
            or unreal_receipt.get("transform_channel_count") != 9
            or unreal_receipt.get("frame_numbers") != [0, 60, 119]
        ):
            raise ValueError("camera-move Sequencer topology changed")
        key_counts = unreal_receipt.get("keys_per_channel")
        if not isinstance(key_counts, dict) or set(key_counts.values()) != {3}:
            raise ValueError("camera-move key counts changed")
        preview_paths = unreal_receipt.get("preview_paths")
        preview_sha256s = unreal_receipt.get("preview_sha256s")
        if not isinstance(preview_paths, dict) or not isinstance(preview_sha256s, dict):
            raise ValueError("camera-move previews are incomplete")
        for label in ("start", "middle", "end"):
            screenshot = roots["camera_move"] / str(preview_paths.get(label))
            if _file_sha256(screenshot) != preview_sha256s.get(label):
                raise ValueError(f"Unreal camera-move {label} preview identity changed")

    if work.material_variation_request_sha256 is not None:
        request = MaterialVariationRequest.model_validate_json(
            (roots["material_variation"] / "material-variation-request.json").read_text(
                encoding="utf-8"
            )
        )
        blender_receipt = BlenderMaterialVariationReceipt.model_validate_json(
            (roots["material_variation"] / "blender-material-variation-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if request.request_sha256 != work.material_variation_request_sha256:
            raise ValueError("registered material-variation request changed")
        if blender_receipt.receipt_sha256 != work.blender_material_variation_receipt_sha256:
            raise ValueError("registered Blender material-variation receipt changed")
        verify_material_variation(request, blender_receipt, roots["material_variation"])
        unreal_receipt = _load_receipt(
            roots["material_variation"] / "unreal-material-variation-receipt.json",
            expected_sha256=str(work.unreal_material_variation_receipt_sha256),
        )
        if unreal_receipt.get("request_sha256") != request.request_sha256:
            raise ValueError("Unreal material variation references another request")
        if unreal_receipt.get("blender_receipt_sha256") != blender_receipt.receipt_sha256:
            raise ValueError("Unreal material variation references another Blender receipt")
        density_receipt = json.loads(
            (roots["density"] / "unreal-native-pcg-density-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if unreal_receipt.get("source_candidate_scene_path") != density_receipt.get(
            "candidate_scene_path"
        ):
            raise ValueError("material candidate no longer derives from native PCG")
        if (
            work.simulation_cache_request_sha256 is None
            and work.foliage_kit_request_sha256 is None
            and work.modular_environment_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("Unreal material candidate changed")
        if unreal_receipt.get("status") != "reconciled":
            raise ValueError("Unreal material variation is not reconciled")
        if unreal_receipt.get("assigned_component_count") != 3:
            raise ValueError("material variation component count changed")
        counts = unreal_receipt.get("generated_instance_counts")
        if not isinstance(counts, dict) or sum(counts.values()) != 12:
            raise ValueError("material variation instance count changed")
        instances = unreal_receipt.get("material_instance_paths")
        if not isinstance(instances, dict) or set(instances) != {
            "wayfinder-a",
            "wayfinder-b",
            "wayfinder-c",
        }:
            raise ValueError("material variation instance identities changed")
        screenshot = roots["material_variation"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal material-variation screenshot identity changed")

    if work.simulation_cache_request_sha256 is not None:
        request = SimulationCacheRequest.model_validate_json(
            (roots["simulation_cache"] / "simulation-cache-request.json").read_text(
                encoding="utf-8"
            )
        )
        blender_receipt = BlenderSimulationCacheReceipt.model_validate_json(
            (roots["simulation_cache"] / "blender-simulation-cache-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if request.request_sha256 != work.simulation_cache_request_sha256:
            raise ValueError("registered simulation-cache request changed")
        if blender_receipt.receipt_sha256 != work.blender_simulation_cache_receipt_sha256:
            raise ValueError("registered Blender simulation-cache receipt changed")
        _verify_artifacts(roots["simulation_cache"], blender_receipt.model_dump(mode="json"))
        unreal_receipt = _load_receipt(
            roots["simulation_cache"] / "unreal-simulation-cache-receipt.json",
            expected_sha256=str(work.unreal_simulation_cache_receipt_sha256),
        )
        terrain_receipt = json.loads(
            (roots["terrain"] / "unreal-biome-terrain-receipt.json").read_text(encoding="utf-8")
        )
        if unreal_receipt.get("source_candidate_scene_path") != terrain_receipt.get(
            "candidate_scene_path"
        ):
            raise ValueError("simulation-cache source terrain candidate changed")
        if (
            work.foliage_kit_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("simulation-cache candidate changed")
        if unreal_receipt.get("status") != "reconciled":
            raise ValueError("Unreal simulation cache is not reconciled")
        if (
            unreal_receipt.get("cache_binding_count"),
            unreal_receipt.get("geometry_cache_track_count"),
            unreal_receipt.get("geometry_cache_section_count"),
        ) != (1, 1, 1):
            raise ValueError("simulation-cache Sequencer topology changed")
        if unreal_receipt.get("duplicate_asset_count") != 0:
            raise ValueError("simulation-cache replay created duplicate assets")
        screenshot = roots["simulation_cache"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal simulation-cache screenshot identity changed")

    if work.foliage_kit_request_sha256 is not None:
        request = FoliageKitRequest.model_validate_json(
            (roots["foliage"] / "foliage-kit-request.json").read_text(encoding="utf-8")
        )
        blender_receipt = _load_receipt(
            roots["foliage"] / "blender-foliage-kit-receipt.json",
            expected_sha256=str(work.blender_foliage_kit_receipt_sha256),
        )
        if request.request_sha256 != work.foliage_kit_request_sha256:
            raise ValueError("registered biome-foliage request changed")
        _verify_artifacts(roots["foliage"], blender_receipt)
        unreal_receipt = _load_receipt(
            roots["foliage"] / "unreal-biome-foliage-receipt.json",
            expected_sha256=str(work.unreal_foliage_kit_receipt_sha256),
        )
        if unreal_receipt.get("request_sha256") != request.request_sha256:
            raise ValueError("Unreal foliage references another request")
        if (
            work.modular_environment_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("biome-foliage candidate changed")
        if (
            unreal_receipt.get("status") != "reconciled"
            or unreal_receipt.get("foliage_instance_count") != 18
        ):
            raise ValueError("biome-foliage instance result changed")
        if set(unreal_receipt.get("mesh_paths", {})) != {"reed", "fern", "broadleaf"}:
            raise ValueError("biome-foliage species identities changed")
        if any(value != 2 for value in unreal_receipt.get("lod_counts", {}).values()):
            raise ValueError("biome-foliage LOD result changed")
        if unreal_receipt.get("duplicate_side_effect_count") != 0:
            raise ValueError("biome-foliage replay created duplicate assets")
        screenshot = roots["foliage"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal biome-foliage screenshot identity changed")

    if work.modular_environment_request_sha256 is not None:
        request = ModularEnvironmentRequest.model_validate_json(
            (roots["modular"] / "modular-environment-request.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.modular_environment_request_sha256:
            raise ValueError("registered modular-environment request changed")
        zone = _load_receipt(
            roots["modular"] / "comfy-module-zone-receipt.json",
            expected_sha256=str(work.comfy_module_zone_receipt_sha256),
        )
        blender_receipt = _load_receipt(
            roots["modular"] / "blender-modular-environment-receipt.json",
            expected_sha256=str(work.blender_modular_environment_receipt_sha256),
        )
        _verify_artifacts(roots["modular"], blender_receipt)
        unreal_receipt = _load_receipt(
            roots["modular"] / "unreal-modular-environment-receipt.json",
            expected_sha256=str(work.unreal_modular_environment_receipt_sha256),
        )
        if zone.get("request_sha256") != request.request_sha256:
            raise ValueError("registered module-zone receipt changed")
        if blender_receipt.get("zone_receipt_sha256") != zone.get("receipt_sha256"):
            raise ValueError("registered Blender modular receipt changed")
        if (
            work.spline_infrastructure_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("modular-environment candidate changed")
        if (
            unreal_receipt.get("status") != "reconciled"
            or unreal_receipt.get("module_actor_count") != 12
        ):
            raise ValueError("modular-environment actor result changed")
        if set(unreal_receipt.get("mesh_paths", {})) != {"wall", "pillar", "gateway"}:
            raise ValueError("modular-environment module identities changed")
        if (
            unreal_receipt.get("created_actor_count") != 0
            or unreal_receipt.get("duplicate_side_effect_count") != 0
        ):
            raise ValueError("modular-environment replay created duplicate actors")
        screenshot = roots["modular"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal modular-environment screenshot identity changed")

    if work.spline_infrastructure_request_sha256 is not None:
        request = SplineInfrastructureRequest.model_validate_json(
            (roots["spline"] / "spline-infrastructure-request.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.spline_infrastructure_request_sha256:
            raise ValueError("registered spline-infrastructure request changed")
        corridor = _load_receipt(
            roots["spline"] / "comfy-route-corridor-receipt.json",
            expected_sha256=str(work.comfy_route_corridor_receipt_sha256),
        )
        blender_receipt = _load_receipt(
            roots["spline"] / "blender-spline-infrastructure-receipt.json",
            expected_sha256=str(work.blender_spline_infrastructure_receipt_sha256),
        )
        _verify_artifacts(roots["spline"], blender_receipt)
        unreal_receipt = _load_receipt(
            roots["spline"] / "unreal-spline-infrastructure-receipt.json",
            expected_sha256=str(work.unreal_spline_infrastructure_receipt_sha256),
        )
        if corridor.get("request_sha256") != request.request_sha256:
            raise ValueError("registered route-corridor receipt changed")
        if blender_receipt.get("corridor_receipt_sha256") != corridor.get("receipt_sha256"):
            raise ValueError("registered Blender spline receipt changed")
        if unreal_receipt.get("blender_receipt_sha256") != blender_receipt.get("receipt_sha256"):
            raise ValueError("registered Unreal spline receipt changed")
        if (
            work.mechanism_rig_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("spline-infrastructure candidate changed")
        if (
            unreal_receipt.get("status") != "reconciled"
            or unreal_receipt.get("spline_component_count") != 2
            or unreal_receipt.get("control_point_count") != 14
            or unreal_receipt.get("segment_actor_count") != 12
            or unreal_receipt.get("support_actor_count") != 8
        ):
            raise ValueError("spline-infrastructure topology changed")
        if (
            unreal_receipt.get("created_actor_count") != 0
            or unreal_receipt.get("duplicate_side_effect_count") != 0
        ):
            raise ValueError("spline-infrastructure replay created duplicate actors")
        if unreal_receipt.get("source_candidate_sha256_before") != unreal_receipt.get(
            "source_candidate_sha256_after"
        ):
            raise ValueError("spline infrastructure changed its source candidate")
        screenshot = roots["spline"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal spline-infrastructure screenshot identity changed")

    if work.mechanism_rig_request_sha256 is not None:
        request = MechanismRigRequest.model_validate_json(
            (roots["mechanism"] / "mechanism-rig-request.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.mechanism_rig_request_sha256:
            raise ValueError("registered mechanism-rig request changed")
        blender_receipt = _load_receipt(
            roots["mechanism"] / "blender-mechanism-rig-receipt.json",
            expected_sha256=str(work.blender_mechanism_rig_receipt_sha256),
        )
        _verify_artifacts(roots["mechanism"], blender_receipt)
        manifest_path = roots["mechanism"] / "AF_ArticulatedGate-manifest.json"
        if _file_sha256(manifest_path) != work.mechanism_manifest_sha256:
            raise ValueError("registered mechanism manifest changed")
        fbx_path = roots["mechanism"] / "SK_AF_ArticulatedGate.fbx"
        if _file_sha256(fbx_path) != work.mechanism_fbx_sha256:
            raise ValueError("registered mechanism FBX changed")
        unreal_receipt = _load_receipt(
            roots["mechanism"] / "unreal-mechanism-rig-receipt.json",
            expected_sha256=str(work.unreal_mechanism_rig_receipt_sha256),
        )
        if unreal_receipt.get("blender_receipt_sha256") != blender_receipt.get("receipt_sha256"):
            raise ValueError("registered Unreal mechanism receipt changed")
        if (
            work.mechanism_shot_request_sha256 is None
            and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("mechanism candidate changed")
        if (
            unreal_receipt.get("status") != "reconciled"
            or unreal_receipt.get("verified_deform_bones") != ["root", "hinge_left", "hinge_right"]
            or unreal_receipt.get("mechanism_actor_count") != 1
        ):
            raise ValueError("mechanism skeleton or candidate result changed")
        if (
            unreal_receipt.get("created_actor_count") != 0
            or unreal_receipt.get("duplicate_side_effect_count") != 0
        ):
            raise ValueError("mechanism replay created duplicate actors")
        if unreal_receipt.get("source_candidate_sha256_before") != unreal_receipt.get(
            "source_candidate_sha256_after"
        ):
            raise ValueError("mechanism return changed its source candidate")
        screenshot = roots["mechanism"] / str(unreal_receipt["screenshot_path"])
        if _file_sha256(screenshot) != unreal_receipt.get("screenshot_sha256"):
            raise ValueError("Unreal mechanism screenshot identity changed")

    if work.mechanism_shot_request_sha256 is not None:
        request = MechanismShotRequest.model_validate_json(
            (roots["mechanism_shot"] / "mechanism-shot-request.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.mechanism_shot_request_sha256:
            raise ValueError("registered mechanism-shot request changed")
        receipt = _load_receipt(
            roots["mechanism_shot"] / "unreal-mechanism-shot-receipt.json",
            expected_sha256=str(work.unreal_mechanism_shot_receipt_sha256),
        )
        if receipt.get("request_sha256") != request.request_sha256:
            raise ValueError("registered Unreal mechanism-shot receipt changed")
        if (
            work.damage_variant_request_sha256 is None
            and receipt.get("candidate_scene_path") != work.candidate_scene_path
        ):
            raise ValueError("mechanism-shot candidate changed")
        if receipt.get("sequence_asset_path") != work.mechanism_shot_sequence_path:
            raise ValueError("mechanism-shot Level Sequence changed")
        if receipt.get("source_candidate_scene_path") != request.source_candidate_scene_path:
            raise ValueError("mechanism shot changed its source candidate")
        if receipt.get("source_candidate_sha256_before") != receipt.get(
            "source_candidate_sha256_after"
        ):
            raise ValueError("mechanism shot mutated its source candidate")
        if (
            receipt.get("status") != "reconciled"
            or receipt.get("animation_track_count") != 1
            or receipt.get("animation_section_count") != 1
            or receipt.get("camera_binding_count") != 1
            or receipt.get("camera_cut_track_count") != 1
            or receipt.get("frame_numbers") != [1, 24, 48]
        ):
            raise ValueError("mechanism-shot sequence topology changed")
        if any(
            receipt.get(field) != 0
            for field in (
                "created_actor_count",
                "created_package_count",
                "created_binding_count",
                "created_track_count",
                "duplicate_track_count",
            )
        ):
            raise ValueError("mechanism-shot replay created duplicate side effects")
        registered_previews = {
            "closed_start": work.mechanism_shot_closed_start_sha256,
            "open": work.mechanism_shot_open_sha256,
            "closed_end": work.mechanism_shot_closed_end_sha256,
        }
        for label, expected in registered_previews.items():
            relative_path = str(receipt["preview_paths"][label])
            path = roots["mechanism_shot"] / relative_path
            if _file_sha256(path) != expected or receipt["preview_sha256s"][label] != expected:
                raise ValueError(f"mechanism-shot {label} preview identity changed")

    if work.damage_variant_request_sha256 is not None:
        request = DamageVariantRequest.model_validate_json(
            (roots["damage"] / "damage-variant-request.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.damage_variant_request_sha256:
            raise ValueError("registered damage-variant request changed")
        comfy_receipt = DamageFieldReceipt.model_validate_json(
            (roots["damage"] / "comfy-damage-field-receipt.json").read_text(encoding="utf-8")
        )
        if (
            comfy_receipt.receipt_sha256 != work.comfy_damage_field_receipt_sha256
            or comfy_receipt.request_sha256 != request.request_sha256
            or comfy_receipt.field_sha256 != work.damage_field_sha256
        ):
            raise ValueError("registered ComfyUI damage field changed")
        field = roots["damage"] / comfy_receipt.field_path
        if _file_sha256(field) != work.damage_field_sha256:
            raise ValueError("damage field artifact identity changed")
        blender_receipt = _load_receipt(
            roots["damage"] / "blender-damage-variant-receipt.json",
            expected_sha256=str(work.blender_damage_variant_receipt_sha256),
        )
        _verify_artifacts(roots["damage"], blender_receipt)
        if (
            blender_receipt.get("request_sha256") != request.request_sha256
            or blender_receipt.get("comfy_receipt_sha256") != comfy_receipt.receipt_sha256
            or blender_receipt.get("boolean_modifier_count") != request.chip_count
            or int(blender_receipt.get("triangle_count", 0)) > request.triangle_budget
            or blender_receipt.get("uv_layer") != "UVMap"
            or not blender_receipt.get("material_slots")
        ):
            raise ValueError("registered Blender damage delivery changed")
        artifacts = {
            str(item["kind"]): item
            for item in blender_receipt.get("artifacts", [])
            if isinstance(item, dict)
        }
        expected_artifacts = {
            "manifest": work.damage_manifest_sha256,
            "glb": work.damage_glb_sha256,
            "material_mask": work.damage_material_mask_sha256,
            "preview": work.damage_blender_preview_sha256,
        }
        if any(
            kind not in artifacts or artifacts[kind].get("sha256") != expected
            for kind, expected in expected_artifacts.items()
        ):
            raise ValueError("registered Blender damage artifact catalog changed")
        modular_receipt = json.loads(
            (roots["modular"] / "unreal-modular-environment-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        if request.source_candidate_scene_path != modular_receipt.get(
            "candidate_scene_path"
        ) or request.source_blender_receipt_sha256 != json.loads(
            (roots["modular"] / "blender-modular-environment-receipt.json").read_text(
                encoding="utf-8"
            )
        ).get("receipt_sha256"):
            raise ValueError("damage route no longer derives from the registered modular result")
        unreal_receipt = _load_receipt(
            roots["damage"] / "unreal-damage-variant-receipt.json",
            expected_sha256=str(work.unreal_damage_variant_receipt_sha256),
        )
        if (
            unreal_receipt.get("request_sha256") != request.request_sha256
            or unreal_receipt.get("comfy_receipt_sha256") != comfy_receipt.receipt_sha256
            or unreal_receipt.get("blender_receipt_sha256") != blender_receipt.get("receipt_sha256")
            or (
                work.cloth_banner_request_sha256 is None
                and unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
            )
            or unreal_receipt.get("status") != "reconciled"
            or unreal_receipt.get("updated_actor_count") != 0
            or unreal_receipt.get("created_actor_count") != 0
            or unreal_receipt.get("duplicate_asset_count") != 0
            or unreal_receipt.get("convex_collision_count", 0) < 1
            or unreal_receipt.get("source_candidate_sha256_before")
            != unreal_receipt.get("source_candidate_sha256_after")
        ):
            raise ValueError("registered Unreal damage result changed")
        preview = roots["damage"] / str(unreal_receipt["screenshot_path"])
        if (
            _file_sha256(preview) != work.damage_unreal_preview_sha256
            or unreal_receipt.get("screenshot_sha256") != work.damage_unreal_preview_sha256
        ):
            raise ValueError("Unreal damage preview identity changed")

    if work.cloth_banner_request_sha256 is not None:
        request = ClothBannerRequest.model_validate_json(
            (roots["cloth_banner"] / "cloth-banner-request.json").read_text(encoding="utf-8")
        )
        if request.request_sha256 != work.cloth_banner_request_sha256:
            raise ValueError("registered cloth-banner request changed")
        comfy_receipt = BannerTextureReceipt.model_validate_json(
            (roots["cloth_banner"] / "comfy-banner-texture-receipt.json").read_text(
                encoding="utf-8"
            )
        )
        texture = roots["cloth_banner"] / comfy_receipt.texture_path
        if (
            comfy_receipt.receipt_sha256 != work.comfy_banner_texture_receipt_sha256
            or comfy_receipt.texture_sha256 != work.banner_texture_sha256
            or _file_sha256(texture) != work.banner_texture_sha256
        ):
            raise ValueError("registered ComfyUI banner texture changed")
        blender_receipt = _load_receipt(
            roots["cloth_banner"] / "blender-cloth-banner-receipt.json",
            expected_sha256=str(work.blender_cloth_banner_receipt_sha256),
        )
        _verify_artifacts(roots["cloth_banner"], blender_receipt)
        if (
            blender_receipt.get("request_sha256") != request.request_sha256
            or blender_receipt.get("comfy_receipt_sha256") != comfy_receipt.receipt_sha256
            or blender_receipt.get("pin_group") != "AF_PinTop"
            or blender_receipt.get("simulation_frame") != request.frame_end
            or int(blender_receipt.get("triangle_count", 0)) > request.triangle_budget
            or not blender_receipt.get("uv_layer")
            or not blender_receipt.get("material")
        ):
            raise ValueError("registered Blender cloth-banner delivery changed")
        artifacts = {
            str(item["kind"]): item
            for item in blender_receipt.get("artifacts", [])
            if isinstance(item, dict)
        }
        expected_artifacts = {
            "blend": work.cloth_banner_blend_sha256,
            "glb": work.cloth_banner_glb_sha256,
            "manifest": work.cloth_banner_manifest_sha256,
            "texture": work.banner_texture_sha256,
            "preview": work.cloth_banner_blender_preview_sha256,
        }
        if any(
            kind not in artifacts or artifacts[kind].get("sha256") != expected
            for kind, expected in expected_artifacts.items()
        ):
            raise ValueError("registered Blender cloth-banner artifact catalog changed")
        unreal_receipt = _load_receipt(
            roots["cloth_banner"] / "unreal-cloth-banner-receipt.json",
            expected_sha256=str(work.unreal_cloth_banner_receipt_sha256),
        )
        if (
            unreal_receipt.get("request_sha256") != request.request_sha256
            or unreal_receipt.get("comfy_receipt_sha256") != comfy_receipt.receipt_sha256
            or unreal_receipt.get("blender_receipt_sha256") != blender_receipt.get("receipt_sha256")
            or unreal_receipt.get("candidate_scene_path") != work.candidate_scene_path
            or unreal_receipt.get("status") != "reconciled"
            or unreal_receipt.get("created_actor_count") != 0
            or unreal_receipt.get("updated_actor_count") != 0
            or unreal_receipt.get("duplicate_asset_count") != 0
            or unreal_receipt.get("material_slot_count", 0) < 1
            or unreal_receipt.get("convex_collision_count", 0) < 1
            or unreal_receipt.get("source_candidate_sha256_before")
            != unreal_receipt.get("source_candidate_sha256_after")
        ):
            raise ValueError("registered Unreal cloth-banner result changed")
        preview = roots["cloth_banner"] / str(unreal_receipt["screenshot_path"])
        if (
            _file_sha256(preview) != work.cloth_banner_unreal_preview_sha256
            or unreal_receipt.get("screenshot_sha256") != work.cloth_banner_unreal_preview_sha256
        ):
            raise ValueError("Unreal cloth-banner preview identity changed")

    return work.unreal_return_receipt_sha256


class SceneDccWorker:
    def __init__(self, store: AgentEventStore, project_root: Path) -> None:
        self._store = store
        self._project_root = project_root.resolve()

    def run_once(self, run_id: str) -> None:
        state = self._store.load(run_id)
        work = state.scene_dcc_work
        if work is None:
            raise AgentRuntimeError("current Scene Session has no DCC work")
        if work.status == "succeeded":
            return
        if work.status == "failed":
            raise AgentRuntimeError("DCC work has failed and requires a new work identity")
        if work.status == "queued":
            self._store.claim_scene_dcc_work(
                run_id,
                work_sha256=work.definition.work_sha256,
                worker_id=WORKER_ID,
            )
            work = self._store.load(run_id).scene_dcc_work
            assert work is not None
        if work.worker_id != WORKER_ID:
            raise AgentRuntimeError("DCC work is owned by another worker")

        try:
            if work.status == "claimed":
                self._progress(run_id, work.definition, "executing", "正在核对固定 DCC 能力链")
                work = self._store.load(run_id).scene_dcc_work
                assert work is not None
            outcome = reconcile_registered_chain(self._project_root, work.definition)
            if work.status == "executing":
                self._progress(
                    run_id, work.definition, "reconciling", "正在对账 Blender 与 Unreal 回执"
                )
            work = self._store.load(run_id).scene_dcc_work
            assert work is not None
            if work.status == "reconciling":
                self._progress(
                    run_id,
                    work.definition,
                    "succeeded",
                    "DCC、ComfyUI、原生 PCG、材质、镜头与动画缓存已回流",
                    outcome_sha256=outcome,
                )
        except (OSError, TypeError, ValueError) as exc:
            current = self._store.load(run_id).scene_dcc_work
            if current is not None and current.status in {"claimed", "executing", "reconciling"}:
                self._progress(run_id, current.definition, "failed", str(exc)[:500])
            raise

    def _progress(
        self,
        run_id: str,
        definition: SceneDccWorkDefinition,
        status: str,
        message: str,
        *,
        outcome_sha256: str | None = None,
    ) -> None:
        self._store.progress_scene_dcc_work(
            run_id,
            SceneDccWorkProgressRequest(
                work_sha256=definition.work_sha256,
                worker_id=WORKER_ID,
                status=status,
                action_id=f"{definition.work_id}-{status}",
                outcome_sha256=outcome_sha256,
                message=message,
            ),
        )
