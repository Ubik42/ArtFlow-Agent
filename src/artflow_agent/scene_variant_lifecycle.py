from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

from .scene_disposition import (
    SceneCandidateAdoptionDecision,
    SceneVariantPublishReceipt,
    SceneVariantPublishRequest,
)
from .scene_session import (
    SceneCandidateDomainEvaluation,
    SceneCandidatePlan,
    SceneSession,
    SceneStageRequest,
)
from .scene_variant_review import (
    SceneVariantLineage,
    SceneVariantReviewReceipt,
    SceneVariantReviewRequest,
    compile_scene_variant_lineage,
)


class SceneCandidateEvaluationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage_request: SceneStageRequest
    failed_plan: SceneCandidatePlan
    failed_evaluation: SceneCandidateDomainEvaluation
    corrected_plan: SceneCandidatePlan
    corrected_evaluation: SceneCandidateDomainEvaluation

    @model_validator(mode="after")
    def verify_chain(self) -> SceneCandidateEvaluationRecord:
        plans = (self.failed_plan, self.corrected_plan)
        evaluations = (self.failed_evaluation, self.corrected_evaluation)
        for plan, evaluation in zip(plans, evaluations, strict=True):
            if plan.stage_request_sha256 != self.stage_request.request_sha256:
                raise ValueError("candidate plan references another stage request")
            if evaluation.plan_sha256 != plan.plan_sha256:
                raise ValueError("domain evaluation references another candidate plan")
            if evaluation.candidate_scene != self.stage_request.candidate_destination:
                raise ValueError("domain evaluation references another candidate scene")
        if self.failed_evaluation.status != "correction_required":
            raise ValueError("first candidate evaluation must require correction")
        if self.corrected_evaluation.status != "accepted":
            raise ValueError("corrected candidate evaluation must be accepted")
        return self


class SceneCandidateAdoptionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: SceneCandidateAdoptionDecision


class SceneVariantPublishRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: SceneVariantPublishRequest
    receipt: SceneVariantPublishReceipt

    @model_validator(mode="after")
    def verify_chain(self) -> SceneVariantPublishRecord:
        if (
            self.receipt.request_sha256 != self.request.request_sha256
            or self.receipt.decision_sha256 != self.request.decision.decision_sha256
            or self.receipt.candidate_scene != self.request.decision.candidate_scene
            or self.receipt.published_scene != self.request.decision.published_scene
        ):
            raise ValueError("publish receipt references another publish request")
        if self.receipt.status != "reconciled":
            raise ValueError("durable publish record requires a reconciled receipt")
        return self


class SceneVariantReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request: SceneVariantReviewRequest
    receipt: SceneVariantReviewReceipt
    lineage: SceneVariantLineage

    @model_validator(mode="after")
    def verify_chain(self) -> SceneVariantReviewRecord:
        if self.receipt.review_sha256 != self.request.review_sha256:
            raise ValueError("review receipt references another review request")
        if self.receipt.status != "reconciled":
            raise ValueError("durable review record requires a reconciled receipt")
        return self


class RegisteredSceneVariantLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation: SceneCandidateEvaluationRecord
    adoption: SceneCandidateAdoptionRecord
    publication: SceneVariantPublishRecord
    review: SceneVariantReviewRecord


def validate_session_binding(
    record: SceneCandidateEvaluationRecord,
    *,
    run_id: str,
    scene_package_sha256: str,
    session: SceneSession,
) -> None:
    request = record.stage_request
    if request.run_id != run_id or session.run_id != run_id:
        raise ValueError("scene variant lifecycle references another run")
    if request.session_id != session.session_id or request.session_sha256 != session.session_sha256:
        raise ValueError("scene variant lifecycle references another Scene Session")
    if request.scene_package_sha256 != scene_package_sha256:
        raise ValueError("scene variant lifecycle references another Scene Package")
    if request.draft_sha256 != session.draft.draft_sha256:
        raise ValueError("scene variant lifecycle references another Session draft")
    if request.basis_sequence != session.draft.basis_sequence + 1:
        raise ValueError("scene variant lifecycle stage request sequence is invalid")
    for plan in (record.failed_plan, record.corrected_plan):
        if (
            plan.run_id != run_id
            or plan.session_sha256 != session.session_sha256
            or plan.scene_package_sha256 != scene_package_sha256
            or plan.draft_sha256 != session.draft.draft_sha256
        ):
            raise ValueError("scene variant candidate plan escaped the persisted Session")


def load_registered_m16_lifecycle(project_root: Path) -> RegisteredSceneVariantLifecycle:
    """Load only the project-owned M12-M16 receipt set; callers cannot supply paths."""

    goal = project_root / "artifacts" / "goal"

    def read(path: Path) -> dict[str, object]:
        return json.loads(path.read_text(encoding="utf-8-sig"))

    handshake = read(goal / "m12-s2-live-candidate-v2" / "scene-handshake-receipt.json")
    artflow_receipt = handshake["artflow_receipt"]
    if not isinstance(artflow_receipt, dict):
        raise ValueError("registered M12 handshake receipt is invalid")
    stage_request = SceneStageRequest.model_validate(artflow_receipt["stage_request"])
    failed_plan = SceneCandidatePlan.model_validate(
        read(goal / "m13-s2-sunlit-overgrown" / "failure-candidate-plan.json")
    )
    corrected_plan = SceneCandidatePlan.model_validate(
        read(goal / "m13-s2-sunlit-overgrown" / "corrected-candidate-plan.json")
    )
    failed = SceneCandidateDomainEvaluation.model_validate(
        read(goal / "m13-s2-sunlit-overgrown" / "failure-domain-evaluation.json")
    )
    corrected = SceneCandidateDomainEvaluation.model_validate(
        read(goal / "m13-s2-sunlit-overgrown" / "corrected-domain-evaluation.json")
    )
    publish_request = SceneVariantPublishRequest.model_validate(
        read(goal / "m15-s1-session-publish" / "publish-request.json")
    )
    publish_receipt = SceneVariantPublishReceipt.model_validate(
        read(goal / "m15-s1-session-publish" / "publish-reconcile-receipt.json")
    )
    review_request = SceneVariantReviewRequest.model_validate(
        read(goal / "m16-s1-variant-lineage" / "review-request.json")
    )
    review_receipt = SceneVariantReviewReceipt.model_validate(
        read(goal / "m16-s1-variant-lineage" / "review-reconcile-receipt.json")
    )
    lineage = compile_scene_variant_lineage(
        failed=failed,
        corrected=corrected,
        publish_request=publish_request,
        publish_receipt=publish_receipt,
        review_request=review_request,
        review_receipt=review_receipt,
    )
    return RegisteredSceneVariantLifecycle(
        evaluation=SceneCandidateEvaluationRecord(
            stage_request=stage_request,
            failed_plan=failed_plan,
            failed_evaluation=failed,
            corrected_plan=corrected_plan,
            corrected_evaluation=corrected,
        ),
        adoption=SceneCandidateAdoptionRecord(decision=publish_request.decision),
        publication=SceneVariantPublishRecord(
            request=publish_request,
            receipt=publish_receipt,
        ),
        review=SceneVariantReviewRecord(
            request=review_request,
            receipt=review_receipt,
            lineage=lineage,
        ),
    )
