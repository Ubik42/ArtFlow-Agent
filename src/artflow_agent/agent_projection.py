from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, BaseModel, model_validator

from .adoption import CandidateAdoptionDecision
from .agent_harness import CapabilityDescription, build_offline_registry
from .agent_runtime import (
    AgentEvent,
    AgentEventStore,
    AgentStatusBar,
    PendingDecision,
    ProviderExecutionLedgerEntry,
)
from .attestation import CapabilityAttestation
from .bounded_revision import BoundedRevisionRequest, BoundedRevisionResult
from .comparison import (
    ComparisonAuthorizationDecision,
    ProviderComparisonManifest,
    ProviderComparisonPlan,
)
from .contracts import CodexImageCandidateRecord
from .current_scene_evaluation import CurrentCandidateEvaluationRecord
from .harness_contracts import HarnessScorecard
from .multimodal_critic import MultimodalTribunalReport
from .negative_control import NegativeControlRecord
from .production_memory import MemoryRecord, MemoryScorecard
from .provenance import VerifiedDeliveryRecord
from .recovery_contracts import RecoveryScorecard
from .scene_candidate_work import SceneCandidateWorkState
from .scene_session import SceneSession
from .scene_variant_review import SceneVariantLineage
from .tribunal import TribunalReport


class SceneFactsProjection(BaseModel):
    package_id: str
    source_application: str
    source_application_version: str
    source_scene: str
    archive_sha256: str
    artifact_count: int
    evidence_class: Literal["real_unreal_capture", "verified_scene_archive"]
    art_goal: str
    preserve: list[str]
    prohibit: list[str]
    protected_regions: list[str]
    editable_regions: list[str]
    pass_kinds: list[str]
    camera_resolution: tuple[int, int]


class AgentTimelineItem(BaseModel):
    sequence: int
    event_id: str
    event_type: str
    occurred_at: AwareDatetime
    label: str
    detail: str
    tone: Literal["neutral", "active", "success", "warning", "danger"]


class AgentRunSummary(BaseModel):
    run_id: str
    stage: str
    scene_package_id: str | None
    last_sequence: int
    occurred_at: AwareDatetime
    pending_decision_count: int


class AgentRunProjection(BaseModel):
    schema_id: Literal["agent-run-projection/1"] = "agent-run-projection/1"
    run_id: str
    status: AgentStatusBar
    scene: SceneFactsProjection | None
    pending_decisions: list[PendingDecision]
    timeline: list[AgentTimelineItem]
    capabilities: list[CapabilityDescription]
    route: AgentRouteProjection | None = None
    capability_attestations: list[CapabilityAttestation]
    provider_executions: list[ProviderExecutionLedgerEntry]
    codex_image_candidates: list[CodexImageCandidateRecord]
    tribunal_report: TribunalReport | None = None
    negative_controls: list[NegativeControlRecord]
    multimodal_tribunal: MultimodalTribunalReport | None = None
    adoption_decision: CandidateAdoptionDecision | None = None
    bounded_revision_request: BoundedRevisionRequest | None = None
    bounded_revision_result: BoundedRevisionResult | None = None
    bounded_revision_attempts: list[BoundedRevisionResult]
    recovery_scorecard: RecoveryScorecard | None = None
    memory_records: list[MemoryRecord]
    memory_scorecard: MemoryScorecard | None = None
    harness_scorecard: HarnessScorecard | None = None
    verified_delivery: VerifiedDeliveryRecord | None = None
    comparison_plan: ProviderComparisonPlan | None = None
    comparison_authorization: ComparisonAuthorizationDecision | None = None
    comparison_manifest: ProviderComparisonManifest | None = None
    scene_session: SceneSession | None = None
    scene_candidate_work: SceneCandidateWorkState | None = None
    scene_candidate_intake: CurrentCandidateEvaluationRecord | None = None
    scene_variant_lineage: SceneVariantLineage | None = None


class AgentRouteProjection(BaseModel):
    decision_id: str
    fingerprint: str
    provider_id: str
    model_id: str
    execution_kind: str
    privacy_class: str
    cost_class: str
    privacy_ceiling: str
    max_cost_usd: float
    required_controls: list[str]
    evaluation_evidence: list[str]
    rejected_alternatives: list[dict[str, object]]


class AgentStreamSnapshot(BaseModel):
    status: AgentStatusBar
    pending_decisions: list[PendingDecision]
    last_sequence: int
    comparison_plan: ProviderComparisonPlan | None = None
    comparison_authorization: ComparisonAuthorizationDecision | None = None
    comparison_manifest: ProviderComparisonManifest | None = None
    scene_session: SceneSession | None = None
    scene_candidate_work: SceneCandidateWorkState | None = None
    scene_candidate_intake: CurrentCandidateEvaluationRecord | None = None
    scene_variant_lineage: SceneVariantLineage | None = None


class AgentStreamEnvelope(BaseModel):
    schema_id: Literal["agent-ui-event/1"] = "agent-ui-event/1"
    kind: Literal["run_event", "run_snapshot", "interrupt"]
    run_id: str
    sequence: int
    occurred_at: AwareDatetime
    event: AgentTimelineItem | None = None
    snapshot: AgentStreamSnapshot | None = None

    @model_validator(mode="after")
    def require_kind_payload(self) -> AgentStreamEnvelope:
        if self.kind == "run_event" and self.event is None:
            raise ValueError("run_event requires an event payload")
        if self.kind in {"run_snapshot", "interrupt"} and self.snapshot is None:
            raise ValueError(f"{self.kind} requires a snapshot payload")
        return self


def list_agent_runs(store: AgentEventStore) -> list[AgentRunSummary]:
    summaries: list[AgentRunSummary] = []
    for run_id in store.list_run_ids():
        state = store.load(run_id)
        events = store.events(run_id)
        summaries.append(
            AgentRunSummary(
                run_id=run_id,
                stage=state.stage,
                scene_package_id=state.scene.package.package_id if state.scene else None,
                last_sequence=state.last_sequence,
                occurred_at=events[-1].occurred_at,
                pending_decision_count=len(state.pending_decisions),
            )
        )
    return summaries


def project_agent_run(store: AgentEventStore, run_id: str) -> AgentRunProjection:
    state = store.load(run_id)
    scene = None
    if state.scene is not None:
        package = state.scene.package
        is_real_unreal_capture = (
            package.provenance.application.casefold() == "unreal engine"
            and package.provenance.scene_name.startswith("/Game/")
            and {item.kind for item in package.passes}
            >= {"beauty", "depth", "world_normal", "object_id"}
        )
        scene = SceneFactsProjection(
            package_id=package.package_id,
            source_application=package.provenance.application,
            source_application_version=package.provenance.application_version,
            source_scene=package.provenance.scene_name,
            archive_sha256=state.scene.archive_sha256,
            artifact_count=len(state.scene.artifacts),
            evidence_class=(
                "real_unreal_capture"
                if is_real_unreal_capture
                else "verified_scene_archive"
            ),
            art_goal=package.art_intent.goal,
            preserve=package.art_intent.preserve,
            prohibit=package.art_intent.prohibit,
            protected_regions=[r.region_id for r in package.regions if r.mode == "protected"],
            editable_regions=[r.region_id for r in package.regions if r.mode == "editable"],
            pass_kinds=[item.kind for item in package.passes],
            camera_resolution=(package.camera.width, package.camera.height),
        )
    events = store.events(run_id)
    route = None
    if state.route_decision is not None:
        decision = state.route_decision
        route = AgentRouteProjection(
            decision_id=decision.decision_id,
            fingerprint=decision.approval_fingerprint(),
            provider_id=decision.selected.provider_id,
            model_id=decision.selected.model_id,
            execution_kind=decision.selected.execution_kind,
            privacy_class=decision.selected.privacy_class,
            cost_class=decision.selected.cost_class,
            privacy_ceiling=decision.privacy_ceiling,
            max_cost_usd=decision.max_cost_usd,
            required_controls=list(decision.execution_intent.required_controls),
            evaluation_evidence=list(decision.execution_intent.evaluation_evidence),
            rejected_alternatives=[
                {
                    "provider_id": item.provider_id,
                    "model_id": item.model_id,
                    "reasons": item.reasons,
                }
                for item in decision.rejected
            ],
        )
    return AgentRunProjection(
        run_id=run_id,
        status=state.status_bar(),
        scene=scene,
        pending_decisions=state.pending_decisions,
        timeline=[_project_event(event) for event in events],
        capabilities=build_offline_registry().descriptions(),
        route=route,
        capability_attestations=state.capability_attestations,
        provider_executions=state.provider_executions,
        codex_image_candidates=state.codex_image_candidates,
        tribunal_report=state.tribunal_report,
        negative_controls=state.negative_controls,
        multimodal_tribunal=state.multimodal_tribunal,
        adoption_decision=state.adoption_decision,
        bounded_revision_request=state.bounded_revision_request,
        bounded_revision_result=state.bounded_revision_result,
        bounded_revision_attempts=state.bounded_revision_attempts,
        recovery_scorecard=state.recovery_scorecard,
        memory_records=state.memory_records,
        memory_scorecard=state.memory_scorecard,
        harness_scorecard=state.harness_scorecard,
        verified_delivery=state.verified_delivery,
        comparison_plan=(
            ProviderComparisonPlan.model_validate(state.comparison_plan)
            if state.comparison_plan
            else None
        ),
        comparison_authorization=(
            ComparisonAuthorizationDecision.model_validate(
                state.comparison_authorization
            )
            if state.comparison_authorization
            else None
        ),
        comparison_manifest=(
            ProviderComparisonManifest.model_validate(state.comparison_manifest)
            if state.comparison_manifest
            else None
        ),
        scene_session=(state.scene_sessions[-1] if state.scene_sessions else None),
        scene_candidate_work=state.scene_candidate_work,
        scene_candidate_intake=state.scene_candidate_intake,
        scene_variant_lineage=(
            state.scene_variant_review.lineage if state.scene_variant_review else None
        ),
    )


def project_stream_event(event: AgentEvent) -> AgentStreamEnvelope:
    return AgentStreamEnvelope(
        kind="run_event",
        run_id=event.run_id,
        sequence=event.sequence,
        occurred_at=event.occurred_at,
        event=_project_event(event),
    )


def project_stream_snapshot(store: AgentEventStore, run_id: str) -> AgentStreamEnvelope:
    state = store.load(run_id)
    events = store.events(run_id)
    kind = "interrupt" if state.pending_decisions else "run_snapshot"
    return AgentStreamEnvelope(
        kind=kind,
        run_id=run_id,
        sequence=state.last_sequence,
        occurred_at=events[-1].occurred_at,
        snapshot=AgentStreamSnapshot(
            status=state.status_bar(),
            pending_decisions=state.pending_decisions,
            last_sequence=state.last_sequence,
            comparison_plan=(
                ProviderComparisonPlan.model_validate(state.comparison_plan)
                if state.comparison_plan
                else None
            ),
            comparison_authorization=(
                ComparisonAuthorizationDecision.model_validate(
                    state.comparison_authorization
                )
                if state.comparison_authorization
                else None
            ),
            comparison_manifest=(
                ProviderComparisonManifest.model_validate(state.comparison_manifest)
                if state.comparison_manifest
                else None
            ),
            scene_session=(state.scene_sessions[-1] if state.scene_sessions else None),
            scene_candidate_work=state.scene_candidate_work,
            scene_candidate_intake=state.scene_candidate_intake,
            scene_variant_lineage=(
                state.scene_variant_review.lineage if state.scene_variant_review else None
            ),
        ),
    )


def _project_event(event: AgentEvent) -> AgentTimelineItem:
    labels: dict[str, tuple[str, str, str]] = {
        "run_created": ("Agent run created", "Durable event stream opened", "neutral"),
        "scene_attached": ("Scene package verified", "Content hashes and constraints bound", "success"),
        "iteration_started": ("Agent iteration", "A bounded reasoning cycle began", "active"),
        "tool_call_started": ("Capability invoked", "Typed input validated and budget reserved", "active"),
        "tool_observed": ("Observation verified", "Independent verifier accepted the result", "success"),
        "approval_requested": ("Human decision required", "Execution is paused at an explicit interrupt", "warning"),
        "approval_resolved": ("Human decision recorded", "The persisted interrupt was resolved", "success"),
        "failure_recorded": ("Run failed closed", "Failure evidence was persisted", "danger"),
        "route_proposed": ("Route proposed", "Provider intent passed deterministic routing", "active"),
        "capability_attested": ("Runtime attested", "Observed capability facts were content-bound", "success"),
        "provider_execution_reserved": (
            "Execution reserved",
            "Idempotency and the fingerprinted route were persisted before submission",
            "active",
        ),
        "provider_execution_submitted": (
            "Provider accepted request",
            "The external request identity was bound to the durable ledger",
            "active",
        ),
        "provider_completion_unknown": (
            "Completion unknown",
            "The agent will reconcile provider state without submitting again",
            "warning",
        ),
        "provider_receipt_recorded": (
            "Provider receipt verified",
            "Identity, route fingerprint, and artifact hashes were independently checked",
            "success",
        ),
        "codex_image_candidate_recorded": (
            "Codex candidate normalized",
            "Built-in image output was source-bound, hashed and persisted without an approval interrupt",
            "success",
        ),
        "tribunal_report_recorded": (
            "Independent tribunal recorded",
            "Typed integrity and composition claims were replayably aggregated without adoption",
            "success",
        ),
        "negative_control_recorded": (
            "Attractive-invalid control captured",
            "A real built-in image was isolated as test evidence, never a production candidate",
            "warning",
        ),
        "multimodal_tribunal_recorded": (
            "Multimodal critic reconciled",
            "Aesthetic appeal and constraint failures were persisted with hard-gate precedence",
            "success",
        ),
        "production_candidate_adopted": (
            "Production candidate adopted",
            "Codex selected one eligible artifact from persisted tribunal evidence without an interrupt",
            "success",
        ),
        "bounded_revision_requested": (
            "Bounded revision sealed",
            "Parent, prompt, editable mask and protected regions were persisted before generation",
            "active",
        ),
        "bounded_revision_recorded": (
            "Bounded revision verified",
            "The real image edit was composited with zero changed pixels outside the mask",
            "success",
        ),
        "bounded_revision_corrected": (
            "Revision seam corrected",
            "The first hard-edge composite was preserved and superseded by an inside-mask feathered result",
            "success",
        ),
        "recovery_scorecard_recorded": (
            "Exactly-once recovery verified",
            "The frozen failure matrix passed with no duplicate side effects",
            "success",
        ),
        "memory_proposed": (
            "Production memory proposed",
            "A typed project memory cited durable source events before policy review",
            "active",
        ),
        "memory_activated": (
            "Production memory activated",
            "Deterministic scope, source, version and conflict checks passed",
            "success",
        ),
        "memory_rejected": (
            "Memory proposal rejected",
            "Deterministic governance blocked an unsafe or conflicting proposal",
            "warning",
        ),
        "memory_scorecard_recorded": (
            "Memory governance verified",
            "The frozen conflict and retrieval suite passed with exact citations",
            "success",
        ),
        "harness_scorecard_recorded": (
            "Agent Harness evaluation verified",
            "Context, routing, policy, recovery and memory cases were aggregated with frozen denominators",
            "success",
        ),
        "verified_delivery_recorded": (
            "Verified Unreal delivery recorded",
            "Return receipt and provenance hash chain persisted",
            "success",
        ),
        "comparison_planned": (
            "Comparison ready for review",
            "Two independent provider actions were bound to one scene and intent",
            "warning",
        ),
        "comparison_authorized": (
            "Comparison authorized",
            "The human owner approved both exact action fingerprints",
            "success",
        ),
        "comparison_manifest_recorded": (
            "Comparison evidence recorded",
            "Child outcomes were normalized without choosing a winner",
            "success",
        ),
        "scene_session_started": (
            "Scene Session started",
            "Intent, selected domains and scene identity entered the durable ledger",
            "active",
        ),
        "scene_candidate_work_queued": (
            "候选工作项已进入 Unreal 队列",
            "当前 Session、Stage Request 与 Candidate Plan 已按内容身份封存",
            "active",
        ),
        "scene_candidate_work_claimed": (
            "Unreal 已领取候选工作项",
            "单一编辑器写入者取得本轮候选执行权",
            "active",
        ),
        "scene_candidate_work_progressed": (
            "Unreal 候选执行状态已更新",
            "执行、对账与结果继续写入同一 Scene Session 事件流",
            "active",
        ),
        "scene_candidate_intake_evaluated": (
            "当前候选已通过技术审查",
            "工作回执、源关卡不变量、PCG 预算与同机位回渲已绑定到当前 Session",
            "success",
        ),
        "scene_candidate_evaluated": (
            "场景候选已评价",
            "失败域与修正后的五域结果已绑定到当前 Scene Session",
            "success",
        ),
        "scene_candidate_adopted": (
            "候选已采用",
            "Codex 采用决定已锁定评价与候选内容身份",
            "success",
        ),
        "scene_variant_published": (
            "场景变体已发布",
            "内容寻址的 Published 关卡与 Unreal 回执已持久化",
            "success",
        ),
        "scene_variant_reviewed": (
            "Unreal 审阅完成",
            "独立进程复检结果已进入当前运行的场景变化谱",
            "success",
        ),
    }
    label, detail, tone = labels[event.event_type]
    if event.event_type == "route_proposed":
        decision = event.data.get("decision", {})
        if isinstance(decision, dict) and not decision.get("requires_explicit_approval", True):
            label = "Local route accepted"
            detail = "Bounded local compute passed policy without an approval interrupt"
            tone = "success"
    return AgentTimelineItem(
        sequence=event.sequence,
        event_id=event.event_id,
        event_type=event.event_type,
        occurred_at=event.occurred_at,
        label=label,
        detail=detail,
        tone=tone,  # type: ignore[arg-type]
    )
