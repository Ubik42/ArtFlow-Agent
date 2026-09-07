from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .blender_set_dressing import BlenderSetDressingReceipt, BlenderSetDressingRequest
from .blender_surface import BlenderSurfaceReceipt, BlenderSurfaceRequest
from .lookdev_handoff import BlenderLookdevReceipt, SceneLookdevRequest

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
        ]
    ] = Field(min_length=2, max_length=7)
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
    unreal_return_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_scene_path: str = Field(
        pattern=r"^/Game/ArtFlow/Sessions/AF_[a-f0-9]{12}/Candidates/(?:Blender|Shot|Lookdev|Surface|Dressing)_B_[a-f0-9]{12}$"
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
        if surface_request.lookdev_receipt_sha256 != hashlib.sha256(
            lookdev_receipt_path.read_bytes()
        ).hexdigest():
            raise ValueError("surface bake references another lookdev receipt")
        if surface_receipt.request_sha256 != surface_request.request_sha256:
            raise ValueError("surface receipt references another request")
        if surface_unreal.get("blender_surface_receipt_sha256") != surface_receipt.receipt_sha256:
            raise ValueError("Unreal surface return references another Blender receipt")
        if surface_unreal.get("source_candidate_scene_path") != lookdev_unreal.get(
            "candidate_scene_path"
        ):
            raise ValueError("Unreal surface candidate no longer derives from the lookdev candidate")
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
        if dressing_unreal.get(
            "blender_set_dressing_receipt_sha256"
        ) != dressing_receipt.receipt_sha256:
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
    digest = dcc_work_sha256(payload)
    return SceneDccWorkDefinition(
        **payload,
        work_id=f"dcc-work-{digest[:12]}",
        work_sha256=digest,
    )
