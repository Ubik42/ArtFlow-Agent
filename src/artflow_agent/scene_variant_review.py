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
        segments = self.published_scene.split("/")
        if (
            len(segments) != 6
            or segments[:4] != ["", "Game", "ArtFlow", "Published"]
            or not segments[4].startswith("AF_")
            or len(segments[4]) != 15
            or any(character not in "0123456789abcdef" for character in segments[4][3:])
            or segments[5] != f"V_{self.content_identity_sha256[:12]}"
        ):
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
    kind: Literal[
        "target", "route", "candidate", "evaluation", "correction", "adoption", "publish", "review"
    ]
    label: str
    state: Literal[
        "retained", "selected", "failed", "evaluated", "corrected", "adopted", "published", "inspected"
    ]
    detail: str
    identity: str


class SceneVariantLineage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-variant-lineage/1"] = (
        "artflow-scene-variant-lineage/1"
    )
    lineage_kind: Literal["correction", "routed_dcc"] = "correction"
    case_id: Literal["sunlit-overgrown", "current-session"]
    status: Literal["published"]
    source_scene: str
    candidate_scene: str
    published_scene: str
    content_identity_sha256: str = Field(pattern=SHA256)
    published_level_sha256: str = Field(pattern=SHA256)
    correction_domain: Domain | None = None
    route_id: Literal["cloth_banner", "damage_variant", "mechanism_shot"] | None = None
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

    is_legacy_showcase = len(failed.findings) == 5
    return SceneVariantLineage(
        case_id="sunlit-overgrown" if is_legacy_showcase else "current-session",
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
            VariantLineageStep(index=1, kind="target", label="视觉目标" if is_legacy_showcase else "场景意图", state="retained", detail="GPT Image 2 构图与保持项已绑定" if is_legacy_showcase else "当前 Scene Session 意图与场景约束已绑定", identity=failed.evaluation_sha256[:12]),
            VariantLineageStep(index=2, kind="candidate", label="初次候选", state="failed", detail=f"灯光域未通过，其他 {len(retained)} 域保留", identity=failed.plan_sha256[:12]),
            VariantLineageStep(index=3, kind="correction", label="定向纠正", state="corrected", detail="只重做 lighting，5.5 / 4200K" if is_legacy_showcase else "只重做 lighting，最终双灯光组通过复评", identity=corrected.plan_sha256[:12]),
            VariantLineageStep(index=4, kind="adoption", label="Codex 采用", state="adopted", detail=f"{len(corrected.findings)} 域通过，锁定候选内容身份", identity=decision.decision_sha256[:12]),
            VariantLineageStep(index=5, kind="publish", label="版本发布", state="published", detail="写入唯一 Published 场景变体", identity=decision.content_identity_sha256[:12]),
            VariantLineageStep(index=6, kind="review", label="Unreal 审阅", state="inspected", detail="新进程加载复检，源关卡未保存", identity=review_request.review_sha256[:12]),
        ],
    )


def compile_routed_dcc_variant_lineage(
    *,
    route_id: Literal["cloth_banner", "damage_variant", "mechanism_shot"],
    evaluation_sha256: str,
    route_decision_sha256: str,
    work_sha256: str,
    technical_check_count: int,
    visual_claim_count: int,
    publish_request: SceneVariantPublishRequest,
    publish_receipt: SceneVariantPublishReceipt,
    review_request: SceneVariantReviewRequest,
    review_receipt: SceneVariantReviewReceipt,
) -> SceneVariantLineage:
    decision = publish_request.decision
    if (
        decision.evaluation_sha256 != evaluation_sha256
        or decision.plan_sha256 != route_decision_sha256
        or decision.execution_receipt_sha256 != work_sha256
    ):
        raise ValueError("routed lineage references another evaluation or work result")
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
        raise ValueError("Unreal review facts differ from the routed published decision")
    route_labels = {
        "cloth_banner": "风场旗帜",
        "damage_variant": "破损变体",
        "mechanism_shot": "机关镜头",
    }
    return SceneVariantLineage(
        lineage_kind="routed_dcc",
        case_id="current-session",
        status="published",
        source_scene=decision.source_scene,
        candidate_scene=decision.candidate_scene,
        published_scene=decision.published_scene,
        content_identity_sha256=decision.content_identity_sha256,
        published_level_sha256=publish_receipt.published_level_sha256,
        correction_domain=None,
        route_id=route_id,
        retained_domains=["image", "material", "asset"],
        generated_instance_count=publish_receipt.generated_instance_count,
        duplicate_side_effect_count=publish_receipt.duplicate_side_effect_count,
        source_level_unchanged=True,
        review_status=review_receipt.status,
        review_id=review_request.review_id,
        steps=[
            VariantLineageStep(index=1, kind="target", label="场景意图", state="retained", detail="当前 Scene Session 与源关卡事实已绑定", identity=decision.source_level_sha256[:12]),
            VariantLineageStep(index=2, kind="route", label="能力选路", state="selected", detail=f"选择{route_labels[route_id]}的最短已验证宿主链", identity=route_decision_sha256[:12]),
            VariantLineageStep(index=3, kind="candidate", label="DCC 候选", state="retained", detail="ComfyUI、Blender 与 Unreal 回执汇聚为一个候选", identity=work_sha256[:12]),
            VariantLineageStep(index=4, kind="evaluation", label="独立评价", state="evaluated", detail=f"{technical_check_count} 项硬检查与 {visual_claim_count} 项视觉判断通过", identity=evaluation_sha256[:12]),
            VariantLineageStep(index=5, kind="adoption", label="Codex 采用", state="adopted", detail="锁定精确候选内容身份并发布唯一版本", identity=decision.decision_sha256[:12]),
            VariantLineageStep(index=6, kind="review", label="Unreal 发布复核", state="inspected", detail="独立进程加载 Published 版本，源关卡未保存", identity=review_request.review_sha256[:12]),
        ],
    )
