from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .scene_session import SceneCandidateDomainEvaluation, SceneCandidatePlan

SHA256 = r"^[a-f0-9]{64}$"
DISPOSITION_POLICY_VERSION = "scene-disposition-policy/1"


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SessionCandidateExecutionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-session-candidate-execution-receipt/1"]
    plan_id: str
    plan_sha256: str = Field(pattern=SHA256)
    stage_request_sha256: str = Field(pattern=SHA256)
    source_scene: str
    source_level_sha256_before: str = Field(pattern=SHA256)
    source_level_sha256_after: str = Field(pattern=SHA256)
    source_level_unchanged: Literal[True]
    candidate_scene: str
    candidate_level_sha256: str = Field(pattern=SHA256)
    generated_instance_count: int = Field(ge=0)
    reconciled: bool
    candidate_beauty_path: str
    candidate_beauty_sha256: str = Field(pattern=SHA256)
    completed_at: str

    @model_validator(mode="after")
    def verify_execution(self) -> SessionCandidateExecutionReceipt:
        if self.source_level_sha256_before != self.source_level_sha256_after:
            raise ValueError("candidate execution changed the source level")
        if not self.candidate_scene.startswith("/Game/ArtFlow/Sessions/"):
            raise ValueError("candidate execution escaped the Session namespace")
        return self


class SceneCandidateAdoptionDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-adoption-decision/1"] = (
        "artflow-scene-adoption-decision/1"
    )
    decision_id: str
    decision_sha256: str = Field(pattern=SHA256)
    action: Literal["publish"] = "publish"
    orchestrator: Literal["codex"] = "codex"
    policy_version: Literal["scene-disposition-policy/1"] = DISPOSITION_POLICY_VERSION
    evaluation_sha256: str = Field(pattern=SHA256)
    plan_sha256: str = Field(pattern=SHA256)
    execution_receipt_sha256: str = Field(pattern=SHA256)
    content_identity_sha256: str = Field(pattern=SHA256)
    source_scene: str
    source_level_sha256: str = Field(pattern=SHA256)
    candidate_scene: str
    candidate_level_sha256: str = Field(pattern=SHA256)
    published_scene: str
    rationale: str = Field(min_length=20, max_length=400)

    @model_validator(mode="after")
    def verify_identity(self) -> SceneCandidateAdoptionDecision:
        payload = self.model_dump(
            mode="json", exclude={"schema_id", "decision_id", "decision_sha256"}
        )
        expected = canonical_sha256(payload)
        if self.decision_sha256 != expected:
            raise ValueError("scene adoption decision hash is invalid")
        if self.decision_id != f"scene-adoption-{expected[:16]}":
            raise ValueError("scene adoption decision id is invalid")
        identity_payload = {
            "evaluation_sha256": self.evaluation_sha256,
            "plan_sha256": self.plan_sha256,
            "execution_receipt_sha256": self.execution_receipt_sha256,
            "source_level_sha256": self.source_level_sha256,
            "candidate_level_sha256": self.candidate_level_sha256,
        }
        if self.content_identity_sha256 != canonical_sha256(identity_payload):
            raise ValueError("scene adoption content identity is invalid")
        expected_destination = (
            f"/Game/ArtFlow/Published/AF_{self.candidate_scene.split('/')[4].removeprefix('AF_')}"
            f"/V_{self.content_identity_sha256[:12]}"
        )
        if self.published_scene != expected_destination:
            raise ValueError("published scene is not the content-addressed decision destination")
        return self


class SceneVariantPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-variant-publish-request/1"] = (
        "artflow-scene-variant-publish-request/1"
    )
    request_id: str
    request_sha256: str = Field(pattern=SHA256)
    idempotency_key: str
    decision: SceneCandidateAdoptionDecision
    expected_protected_state_sha256: str = Field(pattern=SHA256)
    expected_material_path: str
    expected_instance_count: int = Field(ge=0)

    @model_validator(mode="after")
    def verify_request(self) -> SceneVariantPublishRequest:
        payload = self.model_dump(
            mode="json", exclude={"schema_id", "request_id", "request_sha256", "idempotency_key"}
        )
        expected = canonical_sha256(payload)
        if self.request_sha256 != expected:
            raise ValueError("scene variant publish request hash is invalid")
        if self.request_id != f"scene-publish-{expected[:16]}":
            raise ValueError("scene variant publish request id is invalid")
        if self.idempotency_key != f"scene-publish:{expected}":
            raise ValueError("scene variant publish idempotency key is invalid")
        return self


class SceneVariantPublishReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-variant-publish-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256)
    decision_sha256: str = Field(pattern=SHA256)
    status: Literal["published", "reconciled"]
    candidate_scene: str
    candidate_level_sha256: str = Field(pattern=SHA256)
    published_scene: str
    published_level_sha256: str = Field(pattern=SHA256)
    source_level_sha256_before: str = Field(pattern=SHA256)
    source_level_sha256_after: str = Field(pattern=SHA256)
    protected_state_sha256: str = Field(pattern=SHA256)
    material_path: str
    generated_instance_count: int = Field(ge=0)
    duplicate_side_effect_count: Literal[0] = 0
    completed_at: str
    receipt_sha256: str = Field(pattern=SHA256)

    @model_validator(mode="after")
    def verify_receipt(self) -> SceneVariantPublishReceipt:
        if self.source_level_sha256_before != self.source_level_sha256_after:
            raise ValueError("scene variant publication changed the source level")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("scene variant publish receipt hash is invalid")
        return self


def compile_adoption_decision(
    *,
    evaluation: SceneCandidateDomainEvaluation,
    plan: SceneCandidatePlan,
    execution: SessionCandidateExecutionReceipt,
    execution_receipt_sha256: str,
    candidate_file: Path,
    source_file: Path,
) -> SceneCandidateAdoptionDecision:
    if evaluation.status != "accepted" or evaluation.failed_domains:
        raise ValueError("only an accepted domain evaluation can be adopted")
    if evaluation.plan_sha256 != plan.plan_sha256:
        raise ValueError("evaluation references another Candidate Plan")
    if evaluation.candidate_scene != plan.candidate_destination:
        raise ValueError("evaluation references another candidate scene")
    if execution.plan_id != plan.plan_id or execution.plan_sha256 != plan.plan_sha256:
        raise ValueError("execution receipt references another Candidate Plan")
    if execution.stage_request_sha256 != plan.stage_request_sha256:
        raise ValueError("execution receipt references another stage request")
    if execution.candidate_scene != plan.candidate_destination:
        raise ValueError("execution receipt references another candidate scene")
    actual_candidate_sha = file_sha256(candidate_file)
    if actual_candidate_sha != execution.candidate_level_sha256:
        raise ValueError("candidate bytes changed after accepted evaluation")
    if file_sha256(source_file) != execution.source_level_sha256_after:
        raise ValueError("source level bytes changed after candidate execution")
    identity_payload = {
        "evaluation_sha256": evaluation.evaluation_sha256,
        "plan_sha256": plan.plan_sha256,
        "execution_receipt_sha256": execution_receipt_sha256,
        "source_level_sha256": execution.source_level_sha256_after,
        "candidate_level_sha256": actual_candidate_sha,
    }
    content_identity = canonical_sha256(identity_payload)
    session_segment = execution.candidate_scene.split("/")[4].removeprefix("AF_")
    payload = {
        "action": "publish",
        "orchestrator": "codex",
        "policy_version": DISPOSITION_POLICY_VERSION,
        "evaluation_sha256": evaluation.evaluation_sha256,
        "plan_sha256": plan.plan_sha256,
        "execution_receipt_sha256": execution_receipt_sha256,
        "content_identity_sha256": content_identity,
        "source_scene": execution.source_scene,
        "source_level_sha256": execution.source_level_sha256_after,
        "candidate_scene": execution.candidate_scene,
        "candidate_level_sha256": actual_candidate_sha,
        "published_scene": (
            f"/Game/ArtFlow/Published/AF_{session_segment}/V_{content_identity[:12]}"
        ),
        "rationale": (
            "五个场景域均已通过独立评价；采用内容身份锁定的修正候选，"
            "发布为版本化场景变体，不覆盖源关卡。"
        ),
    }
    digest = canonical_sha256(payload)
    return SceneCandidateAdoptionDecision(
        decision_id=f"scene-adoption-{digest[:16]}",
        decision_sha256=digest,
        **payload,
    )


def compile_publish_request(
    decision: SceneCandidateAdoptionDecision,
    *,
    protected_state_sha256: str,
    material_path: str,
    instance_count: int,
) -> SceneVariantPublishRequest:
    payload = {
        "decision": decision.model_dump(mode="json"),
        "expected_protected_state_sha256": protected_state_sha256,
        "expected_material_path": material_path,
        "expected_instance_count": instance_count,
    }
    digest = canonical_sha256(payload)
    return SceneVariantPublishRequest(
        request_id=f"scene-publish-{digest[:16]}",
        request_sha256=digest,
        idempotency_key=f"scene-publish:{digest}",
        **payload,
    )
