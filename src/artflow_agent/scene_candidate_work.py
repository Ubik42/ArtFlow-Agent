from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .scene_session import SceneCandidatePlan, SceneStageRequest


SceneCandidateWorkStatus = Literal[
    "queued", "claimed", "executing", "reconciling", "succeeded", "failed"
]
SceneCandidateProgressStatus = Literal[
    "executing", "reconciling", "succeeded", "failed"
]


class SceneCandidateWorkDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-candidate-work/1"] = (
        "artflow-scene-candidate-work/1"
    )
    work_id: str = Field(pattern=r"^scene-work-[a-f0-9]{12}$")
    work_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: str
    session_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    stage_request: SceneStageRequest
    candidate_plan: SceneCandidatePlan

    @model_validator(mode="after")
    def verify_identity(self) -> SceneCandidateWorkDefinition:
        if self.run_id != self.stage_request.run_id or self.run_id != self.candidate_plan.run_id:
            raise ValueError("candidate work references another run")
        if (
            self.session_sha256 != self.stage_request.session_sha256
            or self.session_sha256 != self.candidate_plan.session_sha256
        ):
            raise ValueError("candidate work references another Scene Session")
        if self.candidate_plan.stage_request_sha256 != self.stage_request.request_sha256:
            raise ValueError("candidate work plan references another stage request")
        expected = candidate_work_sha256(
            self.run_id,
            self.session_sha256,
            self.stage_request,
            self.candidate_plan,
        )
        if self.work_sha256 != expected or self.work_id != f"scene-work-{expected[:12]}":
            raise ValueError("candidate work content identity is invalid")
        return self


class SceneCandidateWorkState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: SceneCandidateWorkDefinition
    status: SceneCandidateWorkStatus = "queued"
    worker_id: str | None = None
    outcome_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    message: str | None = Field(default=None, max_length=500)


class SceneCandidateWorkClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-candidate-claim/1"] = (
        "artflow-scene-candidate-claim/1"
    )
    work_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    session_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    worker_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")


class SceneCandidateWorkProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-candidate-progress/1"] = (
        "artflow-scene-candidate-progress/1"
    )
    work_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    worker_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    status: SceneCandidateProgressStatus
    action_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    outcome_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    message: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_terminal_detail(self) -> SceneCandidateWorkProgressRequest:
        if self.status == "succeeded" and self.outcome_sha256 is None:
            raise ValueError("succeeded candidate work requires an outcome identity")
        if self.status == "failed" and not self.message:
            raise ValueError("failed candidate work requires a recovery message")
        return self


def compile_scene_candidate_work(
    run_id: str,
    session_sha256: str,
    stage_request: SceneStageRequest,
    candidate_plan: SceneCandidatePlan,
) -> SceneCandidateWorkDefinition:
    digest = candidate_work_sha256(
        run_id, session_sha256, stage_request, candidate_plan
    )
    return SceneCandidateWorkDefinition(
        work_id=f"scene-work-{digest[:12]}",
        work_sha256=digest,
        run_id=run_id,
        session_sha256=session_sha256,
        stage_request=stage_request,
        candidate_plan=candidate_plan,
    )


def candidate_work_sha256(
    run_id: str,
    session_sha256: str,
    stage_request: SceneStageRequest,
    candidate_plan: SceneCandidatePlan,
) -> str:
    payload = {
        "run_id": run_id,
        "session_sha256": session_sha256,
        "stage_request": stage_request.model_dump(mode="json"),
        "candidate_plan": candidate_plan.model_dump(mode="json"),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
