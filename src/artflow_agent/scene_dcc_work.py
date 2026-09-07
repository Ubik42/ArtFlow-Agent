from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .blender_set_dressing import BlenderSetDressingReceipt, BlenderSetDressingRequest
from .blender_surface import BlenderSurfaceReceipt, BlenderSurfaceRequest
from .camera_move import BlenderCameraMoveReceipt, CameraMoveRequest
from .foliage_kit import FoliageKitRequest
from .lookdev_handoff import BlenderLookdevReceipt, SceneLookdevRequest
from .material_variation import BlenderMaterialVariationReceipt, MaterialVariationRequest
from .modular_environment import ModularEnvironmentRequest
from .pcg_density import PcgDensityReceipt, PcgDensityRequest, file_sha256
from .procedural_kit import ProceduralKitReceipt, ProceduralKitRequest
from .shot_package import ShotPackageRequest
from .simulation_cache import BlenderSimulationCacheReceipt, SimulationCacheRequest
from .surface_detail import (
    BlenderSurfaceDetailReceipt,
    ComfySurfaceDetailReceipt,
    SurfaceDetailRequest,
)

SceneDccWorkStatus = Literal["queued", "claimed", "executing", "reconciling", "succeeded", "failed"]
SceneDccProgressStatus = Literal["executing", "reconciling", "succeeded", "failed"]


class SceneDccWorkDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-dcc-work/1"] = "artflow-scene-dcc-work/1"
    work_id: str = Field(pattern=r"^dcc-work-[a-f0-9]{12}$")
    work_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: str
    session_id: str
    session_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    capability_ids: list[
        Literal[
            "blender.architectural_prop.weathered_shrine.v1",
            "blender.comfy_pbr.assembly.v1",
            "blender.geometry_nodes.shrine_courtyard.v1",
            "blender.shot.rain_breakthrough.v1",
            "blender.lookdev.scene_target.v1",
            "blender.surface.uv_bake.v1",
            "blender.rigidbody.rubble_settle.v1",
            "blender.surface.inlay_projection_bake.v1",
            "blender.geometry_nodes.modular_wayfinder_kit.v1",
            "unreal.pcg.native_density_kit.v1",
            "unreal.sequencer.procedural_environment_shot.v1",
            "blender.camera_move.three_key_dolly.v1",
            "blender.material.scene_conditioned_wayfinder_set.v1",
            "blender.cache.wind_veil.v1",
            "blender.geometry_nodes.biome_foliage_kit.v1",
            "blender.geometry_nodes.modular_environment.v1",
        ]
    ] = Field(min_length=2, max_length=16)
    modeling_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pbr_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    layout_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    layout_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    shot_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    shot_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_shot_return_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    conditioning_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    conditioning_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    accepted_visual_target_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    lookdev_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    lookdev_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_lookdev_return_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    surface_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    surface_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_surface_return_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    set_dressing_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    set_dressing_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    set_dressing_manifest_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_set_dressing_return_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    surface_detail_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    comfy_surface_detail_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    blender_surface_detail_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    unreal_surface_detail_return_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    procedural_kit_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    procedural_kit_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    procedural_kit_manifest_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_procedural_kit_return_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    pcg_density_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    pcg_density_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    pcg_density_spatial_manifest_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_native_pcg_density_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    native_pcg_graph_path: str | None = Field(
        default=None,
        pattern=r"^/Game/ArtFlow/PCG/Generated/PCG_AF_Density_[a-f0-9]{12}\.PCG_AF_Density_[a-f0-9]{12}$",
    )
    shot_package_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_shot_package_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    level_sequence_path: str | None = Field(
        default=None,
        pattern=r"^/Game/ArtFlow/Sequences/Generated/LS_AF_[a-f0-9]{12}\.LS_AF_[a-f0-9]{12}$",
    )
    camera_move_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    blender_camera_move_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_camera_move_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    camera_move_sequence_path: str | None = Field(
        default=None,
        pattern=r"^/Game/ArtFlow/Sequences/Generated/LS_AF_CameraMove_[a-f0-9]{12}\.LS_AF_CameraMove_[a-f0-9]{12}$",
    )
    material_variation_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    blender_material_variation_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    unreal_material_variation_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    simulation_cache_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    blender_simulation_cache_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    unreal_simulation_cache_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    foliage_kit_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    blender_foliage_kit_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_foliage_kit_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    modular_environment_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    comfy_module_zone_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    blender_modular_environment_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    unreal_modular_environment_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[a-f0-9]{64}$"
    )
    unreal_return_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_scene_path: str = Field(
        pattern=r"^/Game/ArtFlow/Sessions/AF_[a-f0-9]{12}/Candidates/(?:Blender|Shot|Lookdev|Surface|Dressing|Detail|Kit|Density|ShotPackage|Material|Simulation|Foliage|Modular)_B_[a-f0-9]{12}$"
    )

    @model_validator(mode="after")
    def verify_identity(self) -> SceneDccWorkDefinition:
        expected = dcc_work_sha256(
            self.model_dump(mode="json", exclude={"work_id", "work_sha256"}, exclude_none=True)
        )
        expected_capabilities = [
            "blender.architectural_prop.weathered_shrine.v1",
            "blender.comfy_pbr.assembly.v1",
        ]
        if self.layout_request_sha256 is not None or self.layout_receipt_sha256 is not None:
            if self.layout_request_sha256 is None or self.layout_receipt_sha256 is None:
                raise ValueError("DCC work requires both Geometry Nodes identities")
            expected_capabilities.append("blender.geometry_nodes.shrine_courtyard.v1")
        shot_identities = (
            self.shot_request_sha256,
            self.shot_receipt_sha256,
            self.unreal_shot_return_receipt_sha256,
        )
        if any(item is not None for item in shot_identities):
            if not all(item is not None for item in shot_identities):
                raise ValueError("DCC work requires every camera-light exchange identity")
            if self.layout_receipt_sha256 is None:
                raise ValueError("camera-light exchange requires the Geometry Nodes layout")
            expected_capabilities.append("blender.shot.rain_breakthrough.v1")
        lookdev_identities = (
            self.conditioning_request_sha256,
            self.conditioning_receipt_sha256,
            self.accepted_visual_target_sha256,
            self.lookdev_request_sha256,
            self.lookdev_receipt_sha256,
            self.unreal_lookdev_return_receipt_sha256,
        )
        if any(item is not None for item in lookdev_identities):
            if not all(item is not None for item in lookdev_identities):
                raise ValueError("DCC work requires every scene-conditioned lookdev identity")
            if self.shot_receipt_sha256 is None:
                raise ValueError("scene-conditioned lookdev requires the camera-light exchange")
            expected_capabilities.append("blender.lookdev.scene_target.v1")
        surface_identities = (
            self.surface_request_sha256,
            self.surface_receipt_sha256,
            self.unreal_surface_return_receipt_sha256,
        )
        if any(item is not None for item in surface_identities):
            if not all(item is not None for item in surface_identities):
                raise ValueError("DCC work requires every surface-bake identity")
            if self.lookdev_receipt_sha256 is None:
                raise ValueError("surface bake requires the scene-conditioned lookdev")
            expected_capabilities.append("blender.surface.uv_bake.v1")
        dressing_identities = (
            self.set_dressing_request_sha256,
            self.set_dressing_receipt_sha256,
            self.set_dressing_manifest_sha256,
            self.unreal_set_dressing_return_receipt_sha256,
        )
        if any(item is not None for item in dressing_identities):
            if not all(item is not None for item in dressing_identities):
                raise ValueError("DCC work requires every set-dressing identity")
            if self.surface_receipt_sha256 is None:
                raise ValueError("set dressing requires the baked surface")
            expected_capabilities.append("blender.rigidbody.rubble_settle.v1")
        detail_identities = (
            self.surface_detail_request_sha256,
            self.comfy_surface_detail_receipt_sha256,
            self.blender_surface_detail_receipt_sha256,
            self.unreal_surface_detail_return_receipt_sha256,
        )
        if any(item is not None for item in detail_identities):
            if not all(item is not None for item in detail_identities):
                raise ValueError("DCC work requires every surface-detail identity")
            if self.set_dressing_receipt_sha256 is None:
                raise ValueError("surface detail requires the registered set dressing")
            expected_capabilities.append("blender.surface.inlay_projection_bake.v1")
        kit_identities = (
            self.procedural_kit_request_sha256,
            self.procedural_kit_receipt_sha256,
            self.procedural_kit_manifest_sha256,
            self.unreal_procedural_kit_return_receipt_sha256,
        )
        if any(item is not None for item in kit_identities):
            if not all(item is not None for item in kit_identities):
                raise ValueError("DCC work requires every procedural-kit identity")
            if self.blender_surface_detail_receipt_sha256 is None:
                raise ValueError("procedural kit requires the scene-conditioned surface detail")
            expected_capabilities.append("blender.geometry_nodes.modular_wayfinder_kit.v1")
        density_identities = (
            self.pcg_density_request_sha256,
            self.pcg_density_receipt_sha256,
            self.pcg_density_spatial_manifest_sha256,
            self.unreal_native_pcg_density_receipt_sha256,
            self.native_pcg_graph_path,
        )
        if any(item is not None for item in density_identities):
            if not all(item is not None for item in density_identities):
                raise ValueError("DCC work requires every native PCG density identity")
            if self.procedural_kit_receipt_sha256 is None:
                raise ValueError("native PCG density requires the registered procedural kit")
            expected_capabilities.append("unreal.pcg.native_density_kit.v1")
        shot_package_identities = (
            self.shot_package_request_sha256,
            self.unreal_shot_package_receipt_sha256,
            self.level_sequence_path,
        )
        if any(item is not None for item in shot_package_identities):
            if not all(item is not None for item in shot_package_identities):
                raise ValueError("DCC work requires every shot-package identity")
            if self.unreal_native_pcg_density_receipt_sha256 is None:
                raise ValueError("shot package requires the registered native PCG candidate")
            expected_capabilities.append("unreal.sequencer.procedural_environment_shot.v1")
        camera_move_identities = (
            self.camera_move_request_sha256,
            self.blender_camera_move_receipt_sha256,
            self.unreal_camera_move_receipt_sha256,
            self.camera_move_sequence_path,
        )
        if any(item is not None for item in camera_move_identities):
            if not all(item is not None for item in camera_move_identities):
                raise ValueError("DCC work requires every camera-move identity")
            if self.unreal_shot_package_receipt_sha256 is None:
                raise ValueError("camera move requires the registered shot package")
            expected_capabilities.append("blender.camera_move.three_key_dolly.v1")
        material_identities = (
            self.material_variation_request_sha256,
            self.blender_material_variation_receipt_sha256,
            self.unreal_material_variation_receipt_sha256,
        )
        if any(item is not None for item in material_identities):
            if not all(item is not None for item in material_identities):
                raise ValueError("DCC work requires every material-variation identity")
            if self.unreal_native_pcg_density_receipt_sha256 is None:
                raise ValueError("material variation requires the native PCG candidate")
            expected_capabilities.append("blender.material.scene_conditioned_wayfinder_set.v1")
        simulation_identities = (
            self.simulation_cache_request_sha256,
            self.blender_simulation_cache_receipt_sha256,
            self.unreal_simulation_cache_receipt_sha256,
        )
        if any(item is not None for item in simulation_identities):
            if not all(item is not None for item in simulation_identities):
                raise ValueError("DCC work requires every simulation-cache identity")
            if self.unreal_material_variation_receipt_sha256 is None:
                raise ValueError("simulation cache requires the registered material route")
            expected_capabilities.append("blender.cache.wind_veil.v1")
        foliage_identities = (
            self.foliage_kit_request_sha256,
            self.blender_foliage_kit_receipt_sha256,
            self.unreal_foliage_kit_receipt_sha256,
        )
        if any(item is not None for item in foliage_identities):
            if not all(item is not None for item in foliage_identities):
                raise ValueError("DCC work requires every biome-foliage identity")
            expected_capabilities.append("blender.geometry_nodes.biome_foliage_kit.v1")
        modular_identities = (
            self.modular_environment_request_sha256,
            self.comfy_module_zone_receipt_sha256,
            self.blender_modular_environment_receipt_sha256,
            self.unreal_modular_environment_receipt_sha256,
        )
        if any(item is not None for item in modular_identities):
            if not all(item is not None for item in modular_identities):
                raise ValueError("DCC work requires every modular-environment identity")
            if self.foliage_kit_request_sha256 is None:
                raise ValueError("modular environment requires the registered foliage route")
            expected_capabilities.append("blender.geometry_nodes.modular_environment.v1")
        if self.capability_ids != expected_capabilities:
            raise ValueError("DCC work capability order does not match its artifacts")
        if self.work_sha256 != expected or self.work_id != f"dcc-work-{expected[:12]}":
            raise ValueError("DCC work content identity is invalid")
        return self


class SceneDccWorkState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: SceneDccWorkDefinition
    status: SceneDccWorkStatus = "queued"
    worker_id: str | None = None
    outcome_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    message: str | None = Field(default=None, max_length=500)


class SceneDccWorkClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-dcc-claim/1"] = "artflow-scene-dcc-claim/1"
    work_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    session_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    worker_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")


class SceneDccWorkProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-dcc-progress/1"] = "artflow-scene-dcc-progress/1"
    work_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    worker_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    status: SceneDccProgressStatus
    action_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    outcome_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    message: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_terminal_detail(self) -> SceneDccWorkProgressRequest:
        if self.status == "succeeded" and self.outcome_sha256 is None:
            raise ValueError("succeeded DCC work requires an outcome identity")
        if self.status == "failed" and not self.message:
            raise ValueError("failed DCC work requires a recovery message")
        return self


def dcc_work_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def compile_current_blender_dcc_work(
    project_root: Path,
    *,
    run_id: str,
    session_id: str,
    session_sha256: str,
) -> SceneDccWorkDefinition:
    model_root = project_root / "artifacts/goal/m23-s1-blender-modeling"
    pbr_root = project_root / "artifacts/goal/m23-s2-blender-pbr"
    modeling_request = json.loads(
        (model_root / "modeling-request.json").read_text(encoding="utf-8")
    )
    pbr_request = json.loads((pbr_root / "pbr-assembly-request.json").read_text(encoding="utf-8"))
    unreal_receipt = json.loads(
        (pbr_root / "unreal-return-receipt.json").read_text(encoding="utf-8")
    )
    if modeling_request["session_id"] != session_id or pbr_request["session_id"] != session_id:
        raise ValueError("Blender DCC artifacts reference another Scene Session")
    if unreal_receipt["request_sha256"] != pbr_request["request_sha256"]:
        raise ValueError("Unreal return does not match the current Blender PBR request")
    if unreal_receipt.get("capture_status") != "completed":
        raise ValueError("Unreal return capture is not complete")

    payload = {
        "schema_id": "artflow-scene-dcc-work/1",
        "run_id": run_id,
        "session_id": session_id,
        "session_sha256": session_sha256,
        "capability_ids": [
            "blender.architectural_prop.weathered_shrine.v1",
            "blender.comfy_pbr.assembly.v1",
        ],
        "modeling_request_sha256": modeling_request["request_sha256"],
        "pbr_request_sha256": pbr_request["request_sha256"],
        "unreal_return_receipt_sha256": unreal_receipt["receipt_sha256"],
        "candidate_scene_path": unreal_receipt["candidate_scene_path"],
    }
    layout_root = project_root / "artifacts/goal/m23-s4-geometry-layout"
    layout_request_path = layout_root / "layout-request.json"
    layout_receipt_path = layout_root / "layout-receipt.json"
    layout_unreal_path = layout_root / "unreal-return-receipt.json"
    if (
        layout_request_path.is_file()
        and layout_receipt_path.is_file()
        and layout_unreal_path.is_file()
    ):
        layout_request = json.loads(layout_request_path.read_text(encoding="utf-8"))
        layout_receipt = json.loads(layout_receipt_path.read_text(encoding="utf-8"))
        layout_unreal = json.loads(layout_unreal_path.read_text(encoding="utf-8"))
        if layout_request["session_id"] != session_id:
            raise ValueError("Geometry Nodes layout references another Scene Session")
        if layout_receipt["request_sha256"] != layout_request["request_sha256"]:
            raise ValueError("Geometry Nodes receipt references another request")
        if layout_unreal["blender_receipt_sha256"] != layout_receipt["receipt_sha256"]:
            raise ValueError("Geometry Nodes Unreal return references another Blender receipt")
        payload["capability_ids"].append("blender.geometry_nodes.shrine_courtyard.v1")
        payload["layout_request_sha256"] = layout_request["request_sha256"]
        payload["layout_receipt_sha256"] = layout_receipt["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = layout_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = layout_unreal["candidate_scene_path"]
    shot_root = project_root / "artifacts/goal/m23-s5-camera-light"
    shot_request_path = shot_root / "shot-request.json"
    shot_receipt_path = shot_root / "shot-receipt.json"
    shot_unreal_path = shot_root / "unreal-shot-return-receipt.json"
    if shot_request_path.is_file() and shot_receipt_path.is_file() and shot_unreal_path.is_file():
        shot_request = json.loads(shot_request_path.read_text(encoding="utf-8"))
        shot_receipt = json.loads(shot_receipt_path.read_text(encoding="utf-8"))
        shot_unreal = json.loads(shot_unreal_path.read_text(encoding="utf-8"))
        if shot_request["session_id"] != session_id:
            raise ValueError("camera-light exchange references another Scene Session")
        if shot_receipt["request_sha256"] != shot_request["request_sha256"]:
            raise ValueError("Blender shot receipt references another request")
        if shot_unreal["blender_shot_receipt_sha256"] != shot_receipt["receipt_sha256"]:
            raise ValueError("Unreal shot return references another Blender receipt")
        if shot_unreal.get("capture_status") != "completed":
            raise ValueError("Unreal shot return capture is not complete")
        payload["capability_ids"].append("blender.shot.rain_breakthrough.v1")
        payload["shot_request_sha256"] = shot_request["request_sha256"]
        payload["shot_receipt_sha256"] = shot_receipt["receipt_sha256"]
        payload["unreal_shot_return_receipt_sha256"] = shot_unreal["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = shot_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = shot_unreal["candidate_scene_path"]
    conditioning_root = project_root / "artifacts/goal/m24-s1-scene-conditioning"
    lookdev_root = project_root / "artifacts/goal/m24-s2-scene-lookdev"
    lookdev_request_path = lookdev_root / "lookdev-request.json"
    lookdev_receipt_path = lookdev_root / "lookdev-receipt.json"
    lookdev_unreal_path = lookdev_root / "unreal-lookdev-return-receipt.json"
    if (
        lookdev_request_path.is_file()
        and lookdev_receipt_path.is_file()
        and lookdev_unreal_path.is_file()
    ):
        lookdev_request = SceneLookdevRequest.model_validate_json(
            lookdev_request_path.read_text(encoding="utf-8")
        )
        lookdev_receipt = BlenderLookdevReceipt.model_validate_json(
            lookdev_receipt_path.read_text(encoding="utf-8")
        )
        lookdev_unreal = json.loads(lookdev_unreal_path.read_text(encoding="utf-8"))
        conditioning_request_path = conditioning_root / "conditioning-request.json"
        conditioning_receipt_path = conditioning_root / "conditioning-receipt.json"
        conditioning_request = json.loads(conditioning_request_path.read_text(encoding="utf-8"))
        if lookdev_request.session_id != session_id:
            raise ValueError("scene-conditioned lookdev references another Scene Session")
        if lookdev_receipt.request_sha256 != lookdev_request.request_sha256:
            raise ValueError("Blender lookdev receipt references another request")
        if lookdev_unreal.get("blender_lookdev_receipt_sha256") != lookdev_receipt.receipt_sha256:
            raise ValueError("Unreal lookdev return references another Blender receipt")
        if lookdev_unreal.get("capture_status") != "completed":
            raise ValueError("Unreal lookdev return capture is not complete")
        if lookdev_request.conditioning_request_sha256 != conditioning_request["request_sha256"]:
            raise ValueError("lookdev request references another conditioning request")
        if (
            lookdev_request.conditioning_receipt_sha256
            != hashlib.sha256(conditioning_receipt_path.read_bytes()).hexdigest()
        ):
            raise ValueError("lookdev conditioning receipt identity changed")
        payload["capability_ids"].append("blender.lookdev.scene_target.v1")
        payload["conditioning_request_sha256"] = lookdev_request.conditioning_request_sha256
        payload["conditioning_receipt_sha256"] = lookdev_request.conditioning_receipt_sha256
        payload["accepted_visual_target_sha256"] = lookdev_request.accepted_artifact_sha256
        payload["lookdev_request_sha256"] = lookdev_request.request_sha256
        payload["lookdev_receipt_sha256"] = lookdev_receipt.receipt_sha256
        payload["unreal_lookdev_return_receipt_sha256"] = lookdev_unreal["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = lookdev_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = lookdev_unreal["candidate_scene_path"]
    surface_root = project_root / "artifacts/goal/m26-s1-surface-bake"
    surface_request_path = surface_root / "surface-request.json"
    surface_receipt_path = surface_root / "surface-receipt.json"
    surface_unreal_path = surface_root / "unreal-surface-return-receipt.json"
    if (
        surface_request_path.is_file()
        and surface_receipt_path.is_file()
        and surface_unreal_path.is_file()
    ):
        surface_request = BlenderSurfaceRequest.model_validate_json(
            surface_request_path.read_text(encoding="utf-8")
        )
        surface_receipt = BlenderSurfaceReceipt.model_validate_json(
            surface_receipt_path.read_text(encoding="utf-8")
        )
        surface_unreal = json.loads(surface_unreal_path.read_text(encoding="utf-8"))
        if surface_request.session_id != session_id:
            raise ValueError("surface bake references another Scene Session")
        if surface_request.lookdev_request_sha256 != payload.get("lookdev_request_sha256"):
            raise ValueError("surface bake references another lookdev request")
        if (
            surface_request.lookdev_receipt_sha256
            != hashlib.sha256(lookdev_receipt_path.read_bytes()).hexdigest()
        ):
            raise ValueError("surface bake references another lookdev receipt")
        if surface_receipt.request_sha256 != surface_request.request_sha256:
            raise ValueError("surface receipt references another request")
        if surface_unreal.get("blender_surface_receipt_sha256") != surface_receipt.receipt_sha256:
            raise ValueError("Unreal surface return references another Blender receipt")
        if surface_unreal.get("source_candidate_scene_path") != lookdev_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError(
                "Unreal surface candidate no longer derives from the lookdev candidate"
            )
        if surface_unreal.get("capture_status") != "completed":
            raise ValueError("Unreal surface return capture is not complete")
        payload["capability_ids"].append("blender.surface.uv_bake.v1")
        payload["surface_request_sha256"] = surface_request.request_sha256
        payload["surface_receipt_sha256"] = surface_receipt.receipt_sha256
        payload["unreal_surface_return_receipt_sha256"] = surface_unreal["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = surface_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = surface_unreal["candidate_scene_path"]
    dressing_root = project_root / "artifacts/goal/m28-s1-set-dressing"
    dressing_request_path = dressing_root / "set-dressing-request.json"
    dressing_receipt_path = dressing_root / "set-dressing-receipt.json"
    dressing_unreal_path = dressing_root / "unreal-set-dressing-return-receipt.json"
    if (
        dressing_request_path.is_file()
        and dressing_receipt_path.is_file()
        and dressing_unreal_path.is_file()
    ):
        dressing_request = BlenderSetDressingRequest.model_validate_json(
            dressing_request_path.read_text(encoding="utf-8")
        )
        dressing_receipt = BlenderSetDressingReceipt.model_validate_json(
            dressing_receipt_path.read_text(encoding="utf-8")
        )
        dressing_unreal = json.loads(dressing_unreal_path.read_text(encoding="utf-8"))
        if dressing_request.session_id != session_id:
            raise ValueError("set dressing references another Scene Session")
        if dressing_request.surface_request_sha256 != payload.get("surface_request_sha256"):
            raise ValueError("set dressing references another surface request")
        if dressing_request.surface_receipt_sha256 != payload.get("surface_receipt_sha256"):
            raise ValueError("set dressing references another surface receipt")
        if dressing_receipt.request_sha256 != dressing_request.request_sha256:
            raise ValueError("set-dressing receipt references another request")
        manifest_artifact = next(
            item for item in dressing_receipt.artifacts if item.kind == "transform_manifest"
        )
        if (
            dressing_unreal.get("blender_set_dressing_receipt_sha256")
            != dressing_receipt.receipt_sha256
        ):
            raise ValueError("Unreal set-dressing return references another Blender receipt")
        if dressing_unreal.get("source_candidate_scene_path") != surface_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError("set-dressing candidate no longer derives from the surface candidate")
        if dressing_unreal.get("capture_status") != "completed":
            raise ValueError("Unreal set-dressing return capture is not complete")
        payload["capability_ids"].append("blender.rigidbody.rubble_settle.v1")
        payload["set_dressing_request_sha256"] = dressing_request.request_sha256
        payload["set_dressing_receipt_sha256"] = dressing_receipt.receipt_sha256
        payload["set_dressing_manifest_sha256"] = manifest_artifact.sha256
        payload["unreal_set_dressing_return_receipt_sha256"] = dressing_unreal["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = dressing_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = dressing_unreal["candidate_scene_path"]
    detail_root = project_root / "artifacts/goal/m30-s1-surface-detail"
    detail_request_path = detail_root / "surface-detail-request.json"
    comfy_detail_path = detail_root / "comfy-surface-detail-receipt.json"
    blender_detail_path = detail_root / "blender-surface-detail-receipt.json"
    unreal_detail_path = detail_root / "unreal-surface-detail-return-receipt.json"
    if all(
        path.is_file()
        for path in (
            detail_request_path,
            comfy_detail_path,
            blender_detail_path,
            unreal_detail_path,
        )
    ):
        detail_request = SurfaceDetailRequest.model_validate_json(
            detail_request_path.read_text(encoding="utf-8")
        )
        comfy_detail = ComfySurfaceDetailReceipt.model_validate_json(
            comfy_detail_path.read_text(encoding="utf-8")
        )
        blender_detail = BlenderSurfaceDetailReceipt.model_validate_json(
            blender_detail_path.read_text(encoding="utf-8")
        )
        unreal_detail = json.loads(unreal_detail_path.read_text(encoding="utf-8"))
        if detail_request.session_id != session_id:
            raise ValueError("surface detail references another Scene Session")
        if comfy_detail.request_sha256 != detail_request.request_sha256:
            raise ValueError("Comfy surface-detail receipt references another request")
        if blender_detail.request_sha256 != detail_request.request_sha256:
            raise ValueError("Blender surface-detail receipt references another request")
        if blender_detail.comfy_receipt_sha256 != comfy_detail.receipt_sha256:
            raise ValueError("Blender surface detail references another Comfy receipt")
        if unreal_detail.get("blender_receipt_sha256") != blender_detail.receipt_sha256:
            raise ValueError("Unreal surface detail references another Blender receipt")
        if unreal_detail.get("source_candidate_scene_path") != dressing_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError("surface-detail candidate no longer derives from set dressing")
        if unreal_detail.get("capture_status") != "completed":
            raise ValueError("Unreal surface-detail return capture is not complete")
        payload["capability_ids"].append("blender.surface.inlay_projection_bake.v1")
        payload["surface_detail_request_sha256"] = detail_request.request_sha256
        payload["comfy_surface_detail_receipt_sha256"] = comfy_detail.receipt_sha256
        payload["blender_surface_detail_receipt_sha256"] = blender_detail.receipt_sha256
        payload["unreal_surface_detail_return_receipt_sha256"] = unreal_detail["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = unreal_detail["receipt_sha256"]
        payload["candidate_scene_path"] = unreal_detail["candidate_scene_path"]
    kit_root = project_root / "artifacts/goal/m32-s1-procedural-kit"
    kit_request_path = kit_root / "procedural-kit-request.json"
    kit_receipt_path = kit_root / "procedural-kit-receipt.json"
    kit_unreal_path = kit_root / "unreal-procedural-kit-return-receipt.json"
    if all(path.is_file() for path in (kit_request_path, kit_receipt_path, kit_unreal_path)):
        kit_request = ProceduralKitRequest.model_validate_json(
            kit_request_path.read_text(encoding="utf-8")
        )
        kit_receipt = ProceduralKitReceipt.model_validate_json(
            kit_receipt_path.read_text(encoding="utf-8")
        )
        kit_unreal = json.loads(kit_unreal_path.read_text(encoding="utf-8"))
        if kit_request.session_id != session_id:
            raise ValueError("procedural kit references another Scene Session")
        if kit_receipt.request_sha256 != kit_request.request_sha256:
            raise ValueError("Blender procedural-kit receipt references another request")
        manifest = next(item for item in kit_receipt.artifacts if item.kind == "manifest")
        if kit_unreal.get("blender_receipt_sha256") != kit_receipt.receipt_sha256:
            raise ValueError("Unreal procedural-kit return references another Blender receipt")
        if kit_unreal.get("source_candidate_scene_path") != unreal_detail.get(
            "candidate_scene_path"
        ):
            raise ValueError("procedural-kit candidate no longer derives from surface detail")
        if kit_unreal.get("capture_status") != "completed":
            raise ValueError("Unreal procedural-kit return capture is not complete")
        payload["capability_ids"].append("blender.geometry_nodes.modular_wayfinder_kit.v1")
        payload["procedural_kit_request_sha256"] = kit_request.request_sha256
        payload["procedural_kit_receipt_sha256"] = kit_receipt.receipt_sha256
        payload["procedural_kit_manifest_sha256"] = manifest.sha256
        payload["unreal_procedural_kit_return_receipt_sha256"] = kit_unreal["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = kit_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = kit_unreal["candidate_scene_path"]
    density_root = project_root / "artifacts/goal/m34-s1-pcg-density"
    density_request_path = density_root / "pcg-density-request.json"
    density_receipt_path = density_root / "pcg-density-receipt.json"
    density_unreal_path = density_root / "unreal-native-pcg-density-receipt.json"
    if all(
        path.is_file() for path in (density_request_path, density_receipt_path, density_unreal_path)
    ):
        density_request = PcgDensityRequest.model_validate_json(
            density_request_path.read_text(encoding="utf-8")
        )
        density_receipt = PcgDensityReceipt.model_validate_json(
            density_receipt_path.read_text(encoding="utf-8")
        )
        density_unreal = json.loads(density_unreal_path.read_text(encoding="utf-8"))
        spatial_path = density_root / density_receipt.spatial_manifest_path
        if density_request.session_id != session_id:
            raise ValueError("native PCG density references another Scene Session")
        if density_request.kit_receipt_sha256 != payload.get("procedural_kit_receipt_sha256"):
            raise ValueError("native PCG density references another procedural kit")
        if density_receipt.request_sha256 != density_request.request_sha256:
            raise ValueError("ComfyUI density receipt references another request")
        if file_sha256(spatial_path) != density_receipt.spatial_manifest_sha256:
            raise ValueError("native PCG spatial manifest identity changed")
        unreal_payload = dict(density_unreal)
        unreal_sha = unreal_payload.pop("receipt_sha256", None)
        if unreal_sha != dcc_work_sha256(unreal_payload):
            raise ValueError("Unreal native PCG receipt identity changed")
        if density_unreal.get("request_sha256") != density_request.request_sha256:
            raise ValueError("Unreal native PCG return references another request")
        if density_unreal.get("density_receipt_sha256") != density_receipt.receipt_sha256:
            raise ValueError("Unreal native PCG return references another ComfyUI receipt")
        if density_unreal.get("spatial_manifest_sha256") != density_receipt.spatial_manifest_sha256:
            raise ValueError("Unreal native PCG return references another spatial manifest")
        if density_unreal.get("source_candidate_scene_path") != kit_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError("native PCG candidate no longer derives from the procedural kit")
        if (
            density_unreal.get("status") != "reconciled"
            or density_unreal.get("capture_status") != "captured"
        ):
            raise ValueError("Unreal native PCG return is not reconciled with captured evidence")
        payload["capability_ids"].append("unreal.pcg.native_density_kit.v1")
        payload["pcg_density_request_sha256"] = density_request.request_sha256
        payload["pcg_density_receipt_sha256"] = density_receipt.receipt_sha256
        payload["pcg_density_spatial_manifest_sha256"] = density_receipt.spatial_manifest_sha256
        payload["unreal_native_pcg_density_receipt_sha256"] = density_unreal["receipt_sha256"]
        payload["native_pcg_graph_path"] = density_unreal["native_pcg_graph_path"]
        payload["unreal_return_receipt_sha256"] = density_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = density_unreal["candidate_scene_path"]
    shot_package_root = project_root / "artifacts/goal/m36-s1-shot-package"
    shot_package_request_path = shot_package_root / "shot-package-request.json"
    shot_package_unreal_path = shot_package_root / "unreal-shot-package-receipt.json"
    if shot_package_request_path.is_file() and shot_package_unreal_path.is_file():
        shot_package_request = ShotPackageRequest.model_validate_json(
            shot_package_request_path.read_text(encoding="utf-8")
        )
        shot_package_unreal = json.loads(shot_package_unreal_path.read_text(encoding="utf-8"))
        if shot_package_request.session_id != session_id:
            raise ValueError("shot package references another Scene Session")
        if shot_package_request.native_pcg_receipt_sha256 != payload.get(
            "unreal_native_pcg_density_receipt_sha256"
        ):
            raise ValueError("shot package references another native PCG candidate")
        shot_unreal_payload = dict(shot_package_unreal)
        shot_unreal_sha = shot_unreal_payload.pop("receipt_sha256", None)
        if shot_unreal_sha != dcc_work_sha256(shot_unreal_payload):
            raise ValueError("Unreal shot-package receipt identity changed")
        if shot_package_unreal.get("request_sha256") != shot_package_request.request_sha256:
            raise ValueError("Unreal shot package references another request")
        if shot_package_unreal.get("source_candidate_scene_path") != density_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError("shot package no longer derives from the native PCG candidate")
        if (
            shot_package_unreal.get("sequence_asset_path")
            != shot_package_request.sequence_asset_path
        ):
            raise ValueError("Unreal shot package references another Level Sequence")
        if (
            shot_package_unreal.get("status") != "reconciled"
            or shot_package_unreal.get("capture_status") != "captured"
        ):
            raise ValueError("Unreal shot package is not reconciled with captured evidence")
        payload["capability_ids"].append("unreal.sequencer.procedural_environment_shot.v1")
        payload["shot_package_request_sha256"] = shot_package_request.request_sha256
        payload["unreal_shot_package_receipt_sha256"] = shot_package_unreal["receipt_sha256"]
        payload["level_sequence_path"] = shot_package_unreal["sequence_asset_path"]
        payload["unreal_return_receipt_sha256"] = shot_package_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = shot_package_unreal["candidate_scene_path"]
    camera_move_root = project_root / "artifacts/goal/m38-s1-camera-move"
    camera_move_request_path = camera_move_root / "camera-move-request.json"
    blender_camera_move_path = camera_move_root / "blender-camera-move-receipt.json"
    unreal_camera_move_path = camera_move_root / "unreal-camera-move-receipt.json"
    if all(
        path.is_file()
        for path in (
            camera_move_request_path,
            blender_camera_move_path,
            unreal_camera_move_path,
        )
    ):
        camera_move_request = CameraMoveRequest.model_validate_json(
            camera_move_request_path.read_text(encoding="utf-8")
        )
        blender_camera_move = BlenderCameraMoveReceipt.model_validate_json(
            blender_camera_move_path.read_text(encoding="utf-8")
        )
        unreal_camera_move = json.loads(unreal_camera_move_path.read_text(encoding="utf-8"))
        if camera_move_request.session_id != session_id:
            raise ValueError("camera move references another Scene Session")
        if camera_move_request.shot_package_request_sha256 != payload.get(
            "shot_package_request_sha256"
        ):
            raise ValueError("camera move references another shot package")
        if camera_move_request.unreal_shot_package_receipt_sha256 != payload.get(
            "unreal_shot_package_receipt_sha256"
        ):
            raise ValueError("camera move references another Unreal shot-package receipt")
        if blender_camera_move.request_sha256 != camera_move_request.request_sha256:
            raise ValueError("Blender camera move references another request")
        unreal_camera_move_payload = dict(unreal_camera_move)
        unreal_camera_move_sha = unreal_camera_move_payload.pop("receipt_sha256", None)
        if unreal_camera_move_sha != dcc_work_sha256(unreal_camera_move_payload):
            raise ValueError("Unreal camera-move receipt identity changed")
        if unreal_camera_move.get("request_sha256") != camera_move_request.request_sha256:
            raise ValueError("Unreal camera move references another request")
        if unreal_camera_move.get("blender_receipt_sha256") != (blender_camera_move.receipt_sha256):
            raise ValueError("Unreal camera move references another Blender receipt")
        if unreal_camera_move.get("source_sequence_path") != payload.get("level_sequence_path"):
            raise ValueError("camera move no longer derives from the shot-package Sequence")
        if unreal_camera_move.get("source_candidate_scene_path") != payload.get(
            "candidate_scene_path"
        ):
            raise ValueError("camera move no longer derives from the shot-package candidate")
        if unreal_camera_move.get("status") != "reconciled":
            raise ValueError("Unreal camera move is not reconciled")
        payload["capability_ids"].append("blender.camera_move.three_key_dolly.v1")
        payload["camera_move_request_sha256"] = camera_move_request.request_sha256
        payload["blender_camera_move_receipt_sha256"] = blender_camera_move.receipt_sha256
        payload["unreal_camera_move_receipt_sha256"] = unreal_camera_move["receipt_sha256"]
        payload["camera_move_sequence_path"] = unreal_camera_move["sequence_asset_path"]
        payload["unreal_return_receipt_sha256"] = unreal_camera_move["receipt_sha256"]
    material_root = project_root / "artifacts/goal/m40-s1-material-variation"
    material_request_path = material_root / "material-variation-request.json"
    material_blender_path = material_root / "blender-material-variation-receipt.json"
    material_unreal_path = material_root / "unreal-material-variation-receipt.json"
    if all(
        path.is_file()
        for path in (material_request_path, material_blender_path, material_unreal_path)
    ):
        material_request = MaterialVariationRequest.model_validate_json(
            material_request_path.read_text(encoding="utf-8")
        )
        material_blender = BlenderMaterialVariationReceipt.model_validate_json(
            material_blender_path.read_text(encoding="utf-8")
        )
        material_unreal = json.loads(material_unreal_path.read_text(encoding="utf-8"))
        if material_request.session_id != session_id:
            raise ValueError("material variation references another Scene Session")
        if material_request.native_pcg_receipt_sha256 != file_sha256(density_unreal_path):
            raise ValueError("material variation references another native PCG receipt")
        if material_blender.request_sha256 != material_request.request_sha256:
            raise ValueError("Blender material variation references another request")
        material_unreal_payload = dict(material_unreal)
        material_unreal_sha = material_unreal_payload.pop("receipt_sha256", None)
        if material_unreal_sha != dcc_work_sha256(material_unreal_payload):
            raise ValueError("Unreal material-variation receipt identity changed")
        if material_unreal.get("request_sha256") != material_request.request_sha256:
            raise ValueError("Unreal material variation references another request")
        if material_unreal.get("blender_receipt_sha256") != material_blender.receipt_sha256:
            raise ValueError("Unreal material variation references another Blender receipt")
        if material_unreal.get("source_candidate_scene_path") != density_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError("material candidate no longer derives from native PCG")
        if (
            material_unreal.get("status") != "reconciled"
            or material_unreal.get("capture_status") != "captured"
        ):
            raise ValueError("Unreal material variation is not reconciled with captured evidence")
        payload["capability_ids"].append("blender.material.scene_conditioned_wayfinder_set.v1")
        payload["material_variation_request_sha256"] = material_request.request_sha256
        payload["blender_material_variation_receipt_sha256"] = material_blender.receipt_sha256
        payload["unreal_material_variation_receipt_sha256"] = material_unreal["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = material_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = material_unreal["candidate_scene_path"]
    simulation_root = project_root / "artifacts/goal/m43-s1-simulation-cache"
    simulation_request_path = simulation_root / "simulation-cache-request.json"
    simulation_blender_path = simulation_root / "blender-simulation-cache-receipt.json"
    simulation_unreal_path = simulation_root / "unreal-simulation-cache-receipt.json"
    if all(
        path.is_file()
        for path in (simulation_request_path, simulation_blender_path, simulation_unreal_path)
    ):
        simulation_request = SimulationCacheRequest.model_validate_json(
            simulation_request_path.read_text(encoding="utf-8")
        )
        simulation_blender = BlenderSimulationCacheReceipt.model_validate_json(
            simulation_blender_path.read_text(encoding="utf-8")
        )
        simulation_unreal = json.loads(simulation_unreal_path.read_text(encoding="utf-8"))
        if simulation_request.session_id != session_id:
            raise ValueError("simulation cache references another Scene Session")
        if simulation_blender.request_sha256 != simulation_request.request_sha256:
            raise ValueError("Blender simulation cache references another request")
        unreal_payload = dict(simulation_unreal)
        unreal_sha = unreal_payload.pop("receipt_sha256", None)
        if unreal_sha != dcc_work_sha256(unreal_payload):
            raise ValueError("Unreal simulation-cache receipt identity changed")
        if simulation_unreal.get("request_sha256") != simulation_request.request_sha256:
            raise ValueError("Unreal simulation cache references another request")
        if simulation_unreal.get("blender_receipt_sha256") != simulation_blender.receipt_sha256:
            raise ValueError("Unreal simulation cache references another Blender receipt")
        terrain_unreal_path = (
            project_root / "artifacts/goal/m42-s1-terrain-biome/unreal-biome-terrain-receipt.json"
        )
        terrain_unreal = json.loads(terrain_unreal_path.read_text(encoding="utf-8"))
        if simulation_unreal.get("source_candidate_scene_path") != terrain_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError("simulation cache no longer derives from the terrain candidate")
        if (
            simulation_unreal.get("status") != "reconciled"
            or simulation_unreal.get("capture_status") != "captured"
        ):
            raise ValueError("Unreal simulation cache is not reconciled with captured evidence")
        payload["capability_ids"].append("blender.cache.wind_veil.v1")
        payload["simulation_cache_request_sha256"] = simulation_request.request_sha256
        payload["blender_simulation_cache_receipt_sha256"] = simulation_blender.receipt_sha256
        payload["unreal_simulation_cache_receipt_sha256"] = simulation_unreal["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = simulation_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = simulation_unreal["candidate_scene_path"]
    foliage_root = project_root / "artifacts/goal/m45-s1-foliage-kit"
    foliage_request_path = foliage_root / "foliage-kit-request.json"
    foliage_blender_path = foliage_root / "blender-foliage-kit-receipt.json"
    foliage_unreal_path = foliage_root / "unreal-biome-foliage-receipt.json"
    if all(
        path.is_file() for path in (foliage_request_path, foliage_blender_path, foliage_unreal_path)
    ):
        foliage_request = FoliageKitRequest.model_validate_json(
            foliage_request_path.read_text(encoding="utf-8")
        )
        foliage_blender = json.loads(foliage_blender_path.read_text(encoding="utf-8"))
        foliage_unreal = json.loads(foliage_unreal_path.read_text(encoding="utf-8"))
        if foliage_request.session_id != session_id:
            raise ValueError("biome foliage references another Scene Session")
        if foliage_blender.get("request_sha256") != foliage_request.request_sha256:
            raise ValueError("Blender foliage references another request")
        if foliage_unreal.get("request_sha256") != foliage_request.request_sha256:
            raise ValueError("Unreal foliage references another request")
        if foliage_unreal.get("blender_receipt_sha256") != foliage_blender.get("receipt_sha256"):
            raise ValueError("Unreal foliage references another Blender receipt")
        terrain_unreal = json.loads(
            (
                project_root
                / "artifacts/goal/m42-s1-terrain-biome/unreal-biome-terrain-receipt.json"
            ).read_text(encoding="utf-8")
        )
        if foliage_unreal.get("source_candidate_scene_path") != terrain_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError("biome foliage no longer derives from the terrain candidate")
        if (
            foliage_unreal.get("status") != "reconciled"
            or foliage_unreal.get("capture_status") != "captured"
        ):
            raise ValueError("Unreal foliage is not reconciled with captured evidence")
        payload["capability_ids"].append("blender.geometry_nodes.biome_foliage_kit.v1")
        payload["foliage_kit_request_sha256"] = foliage_request.request_sha256
        payload["blender_foliage_kit_receipt_sha256"] = foliage_blender["receipt_sha256"]
        payload["unreal_foliage_kit_receipt_sha256"] = foliage_unreal["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = foliage_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = foliage_unreal["candidate_scene_path"]
    modular_root = project_root / "artifacts/goal/m47-s1-modular-environment"
    modular_request_path = modular_root / "modular-environment-request.json"
    modular_zone_path = modular_root / "comfy-module-zone-receipt.json"
    modular_blender_path = modular_root / "blender-modular-environment-receipt.json"
    modular_unreal_path = modular_root / "unreal-modular-environment-receipt.json"
    if all(
        path.is_file()
        for path in (
            modular_request_path,
            modular_zone_path,
            modular_blender_path,
            modular_unreal_path,
        )
    ):
        modular_request = ModularEnvironmentRequest.model_validate_json(
            modular_request_path.read_text(encoding="utf-8")
        )
        module_zone = json.loads(modular_zone_path.read_text(encoding="utf-8"))
        modular_blender = json.loads(modular_blender_path.read_text(encoding="utf-8"))
        modular_unreal = json.loads(modular_unreal_path.read_text(encoding="utf-8"))
        if modular_request.session_id != session_id:
            raise ValueError("modular environment references another Scene Session")
        if module_zone.get("request_sha256") != modular_request.request_sha256:
            raise ValueError("module-zone receipt references another request")
        if modular_blender.get("zone_receipt_sha256") != module_zone.get("receipt_sha256"):
            raise ValueError("Blender modular assembly references another zone receipt")
        if modular_unreal.get("blender_receipt_sha256") != modular_blender.get("receipt_sha256"):
            raise ValueError("Unreal modular assembly references another Blender receipt")
        if modular_unreal.get("source_candidate_scene_path") != foliage_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError("modular environment no longer derives from the foliage candidate")
        if (
            modular_unreal.get("status") != "reconciled"
            or modular_unreal.get("capture_status") != "captured"
        ):
            raise ValueError("Unreal modular environment is not reconciled with captured evidence")
        payload["capability_ids"].append("blender.geometry_nodes.modular_environment.v1")
        payload["modular_environment_request_sha256"] = modular_request.request_sha256
        payload["comfy_module_zone_receipt_sha256"] = module_zone["receipt_sha256"]
        payload["blender_modular_environment_receipt_sha256"] = modular_blender["receipt_sha256"]
        payload["unreal_modular_environment_receipt_sha256"] = modular_unreal["receipt_sha256"]
        payload["unreal_return_receipt_sha256"] = modular_unreal["receipt_sha256"]
        payload["candidate_scene_path"] = modular_unreal["candidate_scene_path"]
    digest = dcc_work_sha256(payload)
    return SceneDccWorkDefinition(
        **payload,
        work_id=f"dcc-work-{digest[:12]}",
        work_sha256=digest,
    )
