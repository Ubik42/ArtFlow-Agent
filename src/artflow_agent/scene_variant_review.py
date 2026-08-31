from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .scene_disposition import (
    SHA256,
    SceneVariantPublishReceipt,
    SceneVariantPublishRequest,
    canonical_sha256,
)
from .scene_session import SceneCandidateDomainEvaluation

Domain = Literal["image", "material", "asset", "pcg", "lighting"]


class SceneVariantReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-variant-review-request/1"] = (
        "artflow-scene-variant-review-request/1"
    )
    review_id: str
    review_sha256: str = Field(pattern=SHA256)
    idempotency_key: str
    publish_request_sha256: str = Field(pattern=SHA256)
    decision_sha256: str = Field(pattern=SHA256)
    content_identity_sha256: str = Field(pattern=SHA256)
    source_scene: Literal["/Game/ArtFlowDemo"]
    source_level_sha256: str = Field(pattern=SHA256)
    published_scene: str
    published_level_sha256: str = Field(pattern=SHA256)
    expected_protected_state_sha256: str = Field(pattern=SHA256)
    expected_material_path: str
    expected_instance_count: int = Field(ge=0)

    @model_validator(mode="after")
    def verify_request(self) -> SceneVariantReviewRequest:
        payload = self.model_dump(
            mode="json",
            exclude={"schema_id", "review_id", "review_sha256", "idempotency_key"},
        )
        expected = canonical_sha256(payload)
        if self.review_sha256 != expected:
            raise ValueError("scene variant review request hash is invalid")
        if self.review_id != f"scene-review-{expected[:16]}":
            raise ValueError("scene variant review id is invalid")
        if self.idempotency_key != f"scene-review:{expected}":
            raise ValueError("scene variant review idempotency key is invalid")
        expected_path = (
            "/Game/ArtFlow/Published/AF_784907467248/"
            f"V_{self.content_identity_sha256[:12]}"
        )
        if self.published_scene != expected_path:
            raise ValueError("review request escaped the registered Published variant")
        return self


class SceneVariantReviewReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-variant-review-receipt/1"]
    review_id: str
    review_sha256: str = Field(pattern=SHA256)
    status: Literal["inspected", "reconciled"]
    engine_version: str
    published_scene: str
    published_level_sha256: str = Field(pattern=SHA256)
    source_level_sha256_before: str = Field(pattern=SHA256)
    source_level_sha256_after: str = Field(pattern=SHA256)
    protected_state_sha256: str = Field(pattern=SHA256)
    material_path: str
    generated_instance_count: int = Field(ge=0)
    source_save_count: Literal[0] = 0
    completed_at: str
    receipt_sha256: str = Field(pattern=SHA256)

    @model_validator(mode="after")
    def verify_receipt(self) -> SceneVariantReviewReceipt:
        if self.source_level_sha256_before != self.source_level_sha256_after:
            raise ValueError("scene review changed the source level")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != canonical_sha256(unsigned):
            raise ValueError("scene variant review receipt hash is invalid")
        return self


class VariantLineageStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1, le=9)
    kind: Literal["target", "candidate", "correction", "adoption", "publish", "review"]
    label: str
    state: Literal["retained", "failed", "corrected", "adopted", "published", "inspected"]
    detail: str
    identity: str


class SceneVariantLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-variant-lineage/1"] = (
        "artflow-scene-variant-lineage/1"
    )
    case_id: Literal["sunlit-overgrown"]
    status: Literal["published"]
    source_scene: str
    candidate_scene: str
    published_scene: str
    content_identity_sha256: str = Field(pattern=SHA256)
    published_level_sha256: str = Field(pattern=SHA256)
    correction_domain: Domain
    retained_domains: list[Domain]
    generated_instance_count: int = Field(ge=0)
    duplicate_side_effect_count: Literal[0]
    source_level_unchanged: Literal[True]
    review_status: Literal["inspected", "reconciled"]
    review_id: str
    steps: list[VariantLineageStep] = Field(min_length=6, max_length=6)


def compile_scene_variant_review_request(
    publish_request: SceneVariantPublishRequest,
    publish_receipt: SceneVariantPublishReceipt,
) -> SceneVariantReviewRequest:
    decision = publish_request.decision
    if publish_receipt.status != "reconciled":
        raise ValueError("review handoff requires a reconciled published variant")
    if (
        publish_receipt.request_sha256 != publish_request.request_sha256
        or publish_receipt.decision_sha256 != decision.decision_sha256
        or publish_receipt.published_scene != decision.published_scene
        or publish_receipt.candidate_level_sha256 != decision.candidate_level_sha256
    ):
        raise ValueError("publish receipt does not belong to the adoption decision")
    payload = {
        "publish_request_sha256": publish_request.request_sha256,
        "decision_sha256": decision.decision_sha256,
        "content_identity_sha256": decision.content_identity_sha256,
        "source_scene": decision.source_scene,
        "source_level_sha256": decision.source_level_sha256,
        "published_scene": decision.published_scene,
        "published_level_sha256": publish_receipt.published_level_sha256,
        "expected_protected_state_sha256": publish_request.expected_protected_state_sha256,
        "expected_material_path": publish_request.expected_material_path,
        "expected_instance_count": publish_request.expected_instance_count,
    }
    digest = canonical_sha256(payload)
    return SceneVariantReviewRequest(
        review_id=f"scene-review-{digest[:16]}",
        review_sha256=digest,
        idempotency_key=f"scene-review:{digest}",
        **payload,
    )


def compile_scene_variant_lineage(
    *,
    failed: SceneCandidateDomainEvaluation,
    corrected: SceneCandidateDomainEvaluation,
    publish_request: SceneVariantPublishRequest,
    publish_receipt: SceneVariantPublishReceipt,
    review_request: SceneVariantReviewRequest,
    review_receipt: SceneVariantReviewReceipt,
) -> SceneVariantLineage:
    if failed.status != "correction_required" or failed.failed_domains != ["lighting"]:
        raise ValueError("lineage requires the frozen lighting-only failure")
    if corrected.status != "accepted" or corrected.failed_domains:
        raise ValueError("lineage requires an accepted corrected evaluation")
    if failed.candidate_scene != corrected.candidate_scene:
        raise ValueError("failure and correction reference different candidates")
    retained: list[Domain] = []
    corrected_by_domain = {item.domain: item for item in corrected.findings}
    for finding in failed.findings:
        after = corrected_by_domain.get(finding.domain)
        if after is None or after.status != "passed":
            raise ValueError("corrected evaluation is incomplete")
        if finding.domain != "lighting":
            if finding.status != "passed" or finding.evidence_sha256 != after.evidence_sha256:
                raise ValueError("a successful domain changed during correction")
            retained.append(finding.domain)
        elif finding.evidence_sha256 == after.evidence_sha256:
            raise ValueError("lighting correction did not produce new evidence")

    decision = publish_request.decision
    if decision.evaluation_sha256 != corrected.evaluation_sha256:
        raise ValueError("adoption decision references another evaluation")
    if review_request.review_sha256 != review_receipt.review_sha256:
        raise ValueError("review receipt references another review request")
    if (
        review_receipt.published_scene != decision.published_scene
        or review_receipt.published_level_sha256 != publish_receipt.published_level_sha256
        or review_receipt.source_level_sha256_after != decision.source_level_sha256
        or review_receipt.protected_state_sha256
        != publish_request.expected_protected_state_sha256
        or review_receipt.material_path != publish_request.expected_material_path
        or review_receipt.generated_instance_count != publish_request.expected_instance_count
    ):
        raise ValueError("Unreal review facts differ from the published decision")

    return SceneVariantLineage(
        case_id="sunlit-overgrown",
        status="published",
        source_scene=decision.source_scene,
        candidate_scene=decision.candidate_scene,
        published_scene=decision.published_scene,
        content_identity_sha256=decision.content_identity_sha256,
        published_level_sha256=publish_receipt.published_level_sha256,
        correction_domain="lighting",
        retained_domains=retained,
        generated_instance_count=publish_receipt.generated_instance_count,
        duplicate_side_effect_count=publish_receipt.duplicate_side_effect_count,
        source_level_unchanged=True,
        review_status=review_receipt.status,
        review_id=review_request.review_id,
        steps=[
            VariantLineageStep(index=1, kind="target", label="视觉目标", state="retained", detail="GPT Image 2 构图与保持项已绑定", identity=failed.evaluation_sha256[:12]),
            VariantLineageStep(index=2, kind="candidate", label="初次候选", state="failed", detail="灯光域未通过，其他四域保留", identity=failed.plan_sha256[:12]),
            VariantLineageStep(index=3, kind="correction", label="定向纠正", state="corrected", detail="只重做 lighting，5.5 / 4200K", identity=corrected.plan_sha256[:12]),
            VariantLineageStep(index=4, kind="adoption", label="Codex 采用", state="adopted", detail="五域通过，锁定候选内容身份", identity=decision.decision_sha256[:12]),
            VariantLineageStep(index=5, kind="publish", label="版本发布", state="published", detail="写入唯一 Published 场景变体", identity=decision.content_identity_sha256[:12]),
            VariantLineageStep(index=6, kind="review", label="Unreal 审阅", state="inspected", detail="新进程加载复检，源关卡未保存", identity=review_request.review_sha256[:12]),
        ],
    )
