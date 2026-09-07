from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SceneDccWorkStatus = Literal[
    "queued", "claimed", "executing", "reconciling", "succeeded", "failed"
]
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
        ]
    ] = Field(min_length=2, max_length=3)
    modeling_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    pbr_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    layout_request_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    layout_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    unreal_return_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_scene_path: str = Field(
        pattern=r"^/Game/ArtFlow/Sessions/AF_[a-f0-9]{12}/Candidates/Blender_B_[a-f0-9]{12}$"
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
    modeling_request = json.loads((model_root / "modeling-request.json").read_text(encoding="utf-8"))
    pbr_request = json.loads((pbr_root / "pbr-assembly-request.json").read_text(encoding="utf-8"))
    unreal_receipt = json.loads((pbr_root / "unreal-return-receipt.json").read_text(encoding="utf-8"))
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
    if layout_request_path.is_file() and layout_receipt_path.is_file() and layout_unreal_path.is_file():
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
    digest = dcc_work_sha256(payload)
    return SceneDccWorkDefinition(
        **payload,
        work_id=f"dcc-work-{digest[:12]}",
        work_sha256=digest,
    )
