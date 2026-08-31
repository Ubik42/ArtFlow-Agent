from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field

from .adoption import CandidateAdoptionDecision
from .attestation import CapabilityAttestation
from .bounded_revision import BoundedRevisionRequest, BoundedRevisionResult
from .contracts import (
    CodexImageCandidateRecord,
    ProviderExecutionReceipt,
    RouteDecision,
    SceneConstraintPackage,
    SceneDigitalTwin,
)
from .harness_contracts import HarnessScorecard
from .multimodal_critic import MultimodalTribunalReport
from .negative_control import NegativeControlRecord
from .production_memory import (
    MemoryPolicyDecision,
    MemoryProposal,
    MemoryRecord,
    MemoryScorecard,
    decide_memory_policy,
)
from .provenance import VerifiedDeliveryRecord
from .recovery_contracts import RecoveryScorecard
from .scene_packages import ScenePackagePreview, VerifiedSceneArtifact
from .scene_session import (
    SceneSession,
    SceneSessionDraft,
    build_scene_session,
    validate_scene_session_draft,
)
from .scene_variant_lifecycle import (
    SceneCandidateAdoptionRecord,
    SceneCandidateEvaluationRecord,
    SceneVariantPublishRecord,
    SceneVariantReviewRecord,
    validate_session_binding,
)
from .scene_variant_review import compile_scene_variant_lineage
from .tribunal import TribunalReport

AgentEventType = Literal[
    "run_created",
    "scene_attached",
    "approval_requested",
    "approval_resolved",
    "failure_recorded",
    "iteration_started",
    "tool_call_started",
    "tool_observed",
    "route_proposed",
    "capability_attested",
    "provider_execution_reserved",
    "provider_execution_submitted",
    "provider_completion_unknown",
    "provider_receipt_recorded",
    "codex_image_candidate_recorded",
    "tribunal_report_recorded",
    "negative_control_recorded",
    "multimodal_tribunal_recorded",
    "production_candidate_adopted",
    "bounded_revision_requested",
    "bounded_revision_recorded",
    "bounded_revision_corrected",
    "recovery_scorecard_recorded",
    "memory_proposed",
    "memory_activated",
    "memory_rejected",
    "memory_scorecard_recorded",
    "harness_scorecard_recorded",
    "verified_delivery_recorded",
    "comparison_planned",
    "comparison_authorized",
    "comparison_manifest_recorded",
    "scene_session_started",
    "scene_candidate_evaluated",
    "scene_candidate_adopted",
    "scene_variant_published",
    "scene_variant_reviewed",
]
AgentStage = Literal[
    "awaiting_scene",
    "route_ready",
    "awaiting_approval",
    "approved",
    "failed",
    "executing",
    "reconciling",
    "execution_succeeded",
]
ApprovalState = Literal["none", "pending", "approved", "rejected"]


class AgentRuntimeError(RuntimeError):
    """Raised when durable Agent state is missing, corrupt, or transitions unsafely."""


class AgentBudget(BaseModel):
    max_iterations: int = Field(default=12, ge=1, le=1000)
    used_iterations: int = Field(default=0, ge=0)
    max_tool_calls: int = Field(default=24, ge=1, le=1000)
    used_tool_calls: int = Field(default=0, ge=0)
    max_retries: int = Field(default=3, ge=0, le=100)
    used_retries: int = Field(default=0, ge=0)
    max_cost_usd: float | None = Field(default=None, ge=0)


class PendingDecision(BaseModel):
    decision_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    kind: Literal["route_approval", "comparison_authorization"] = "route_approval"
    summary: str = Field(min_length=1, max_length=1000)
    fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class SceneAttachment(BaseModel):
    package: SceneConstraintPackage
    archive_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifacts: list[VerifiedSceneArtifact] = Field(min_length=4)
    digital_twin: SceneDigitalTwin | None = None


class PendingToolCall(BaseModel):
    call_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,119}$")
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ToolObservationRecord(BaseModel):
    call_id: str
    capability_id: str
    output_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str = Field(min_length=1, max_length=1000)
    verified: bool
    artifact_ids: list[str] = Field(default_factory=list, max_length=64)


ExecutionLedgerStatus = Literal[
    "reserved",
    "submitted",
    "completion_unknown",
    "succeeded",
    "failed",
    "cancelled",
]


class ProviderExecutionLedgerEntry(BaseModel):
    execution_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    idempotency_key: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,199}$")
    route_decision_id: str
    route_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    attestation_environment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_id: str
    model_id: str
    status: ExecutionLedgerStatus
    provider_request_id: str | None = None
    unknown_reason: str | None = None
    receipt: ProviderExecutionReceipt | None = None


class AgentStatusBar(BaseModel):
    stage: AgentStage
    scene_package_id: str | None
    approval: ApprovalState
    pending_decision_count: int = Field(ge=0)
    pending_tool_call_count: int = Field(ge=0)
    failure_count: int = Field(ge=0)
    budgets: AgentBudget
    artifact_ids: list[str]
    route_decision_id: str | None = None
    route_provider: str | None = None
    route_model: str | None = None
    route_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    capability_attestation_count: int = Field(default=0, ge=0)
    local_provider_status: Literal["supported", "unsupported", "unknown"] | None = None
    execution_status: ExecutionLedgerStatus | None = None
    provider_request_id: str | None = None


class AgentRunState(BaseModel):
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    stage: AgentStage
    created_at: AwareDatetime
    scene: SceneAttachment | None = None
    pending_decisions: list[PendingDecision] = Field(default_factory=list)
    pending_tool_calls: list[PendingToolCall] = Field(default_factory=list)
    observations: list[ToolObservationRecord] = Field(default_factory=list)
    route_decision: RouteDecision | None = None
    capability_attestations: list[CapabilityAttestation] = Field(default_factory=list)
    provider_executions: list[ProviderExecutionLedgerEntry] = Field(default_factory=list)
    codex_image_candidates: list[CodexImageCandidateRecord] = Field(default_factory=list)
    tribunal_report: TribunalReport | None = None
    negative_controls: list[NegativeControlRecord] = Field(default_factory=list)
    multimodal_tribunal: MultimodalTribunalReport | None = None
    adoption_decision: CandidateAdoptionDecision | None = None
    bounded_revision_request: BoundedRevisionRequest | None = None
    bounded_revision_result: BoundedRevisionResult | None = None
    bounded_revision_attempts: list[BoundedRevisionResult] = Field(default_factory=list)
    recovery_scorecard: RecoveryScorecard | None = None
    memory_records: list[MemoryRecord] = Field(default_factory=list)
    memory_scorecard: MemoryScorecard | None = None
    harness_scorecard: HarnessScorecard | None = None
    verified_delivery: VerifiedDeliveryRecord | None = None
    comparison_plan: dict[str, Any] | None = None
    comparison_authorization: dict[str, Any] | None = None
    comparison_manifest: dict[str, Any] | None = None
    scene_sessions: list[SceneSession] = Field(default_factory=list)
    scene_candidate_evaluation: SceneCandidateEvaluationRecord | None = None
    scene_candidate_adoption: SceneCandidateAdoptionRecord | None = None
    scene_variant_publication: SceneVariantPublishRecord | None = None
    scene_variant_review: SceneVariantReviewRecord | None = None
    approval: ApprovalState = "none"
    failures: list[str] = Field(default_factory=list)
    budgets: AgentBudget = Field(default_factory=AgentBudget)
    last_sequence: int = Field(ge=1)

    def status_bar(self) -> AgentStatusBar:
        artifact_ids: list[str] = []
        if self.scene is not None:
            artifact_ids.append(f"archive:sha256:{self.scene.archive_sha256}")
            artifact_ids.extend(
                f"{artifact.path}:sha256:{artifact.sha256}" for artifact in self.scene.artifacts
            )
        return AgentStatusBar(
            stage=self.stage,
            scene_package_id=self.scene.package.package_id if self.scene else None,
            approval=self.approval,
            pending_decision_count=len(self.pending_decisions),
            pending_tool_call_count=len(self.pending_tool_calls),
            failure_count=len(self.failures),
            budgets=self.budgets,
            artifact_ids=artifact_ids,
            route_decision_id=(self.route_decision.decision_id if self.route_decision else None),
            route_provider=(self.route_decision.selected.provider_id if self.route_decision else None),
            route_model=(self.route_decision.selected.model_id if self.route_decision else None),
            route_fingerprint=(
                self.route_decision.approval_fingerprint() if self.route_decision else None
            ),
            capability_attestation_count=len(self.capability_attestations),
            local_provider_status=(
                self.capability_attestations[-1].status
                if self.capability_attestations
                else None
            ),
            execution_status=(
                self.provider_executions[-1].status if self.provider_executions else None
            ),
            provider_request_id=(
                self.provider_executions[-1].provider_request_id
                if self.provider_executions
                else None
            ),
        )


class AgentEvent(BaseModel):
    run_id: str
    sequence: int = Field(ge=1)
    event_id: str
    event_type: AgentEventType
    occurred_at: AwareDatetime
    idempotency_key: str
    data: dict[str, Any]
    previous_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    event_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class _RunCreated(BaseModel):
    budgets: AgentBudget


class _ApprovalRequested(BaseModel):
    decision: PendingDecision


class _ApprovalResolved(BaseModel):
    decision_id: str
    resolution: Literal["approved", "rejected"]


class _FailureRecorded(BaseModel):
    code: str = Field(min_length=1, max_length=120)
    detail: str = Field(min_length=1, max_length=2000)


class _IterationStarted(BaseModel):
    iteration_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")


class _ToolCallStarted(BaseModel):
    call: PendingToolCall


class _ToolObserved(BaseModel):
    observation: ToolObservationRecord


class _RouteProposed(BaseModel):
    decision: RouteDecision


class _CapabilityAttested(BaseModel):
    attestation: CapabilityAttestation


class _ProviderExecutionReserved(BaseModel):
    execution: ProviderExecutionLedgerEntry


class _ProviderExecutionSubmitted(BaseModel):
    execution_id: str
    provider_request_id: str = Field(min_length=1, max_length=300)


class _ProviderCompletionUnknown(BaseModel):
    execution_id: str
    reason: str = Field(min_length=1, max_length=500)


class _ProviderReceiptRecorded(BaseModel):
    receipt: ProviderExecutionReceipt


class _CodexImageCandidateRecorded(BaseModel):
    record: CodexImageCandidateRecord


class _TribunalReportRecorded(BaseModel):
    report: TribunalReport


class _NegativeControlRecorded(BaseModel):
    record: NegativeControlRecord


class _MultimodalTribunalRecorded(BaseModel):
    report: MultimodalTribunalReport


class _ProductionCandidateAdopted(BaseModel):
    decision: CandidateAdoptionDecision


class _BoundedRevisionRequested(BaseModel):
    request: BoundedRevisionRequest


class _BoundedRevisionRecorded(BaseModel):
    result: BoundedRevisionResult


class _RecoveryScorecardRecorded(BaseModel):
    scorecard: RecoveryScorecard


class _MemoryProposed(BaseModel):
    proposal: MemoryProposal


class _MemoryResolved(BaseModel):
    memory_id: str
    decision: MemoryPolicyDecision


class _MemoryScorecardRecorded(BaseModel):
    scorecard: MemoryScorecard


class _VerifiedDeliveryRecorded(BaseModel):
    delivery: VerifiedDeliveryRecord


class _HarnessScorecardRecorded(BaseModel):
    scorecard: HarnessScorecard


class _ComparisonPayload(BaseModel):
    value: dict[str, Any]


class _SceneSessionStarted(BaseModel):
    session: SceneSession


class _SceneCandidateEvaluated(BaseModel):
    record: SceneCandidateEvaluationRecord


class _SceneCandidateAdopted(BaseModel):
    record: SceneCandidateAdoptionRecord


class _SceneVariantPublished(BaseModel):
    record: SceneVariantPublishRecord


class _SceneVariantReviewed(BaseModel):
    record: SceneVariantReviewRecord


class AgentEventStore:
    """SQLite event log whose reducer, not the model, owns authoritative Agent state."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL CHECK (sequence > 0),
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    previous_hash TEXT,
                    event_hash TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence),
                    UNIQUE (run_id, idempotency_key)
                )
                """
            )
            connection.commit()

    def create_run(
        self,
        run_id: str,
        *,
        budgets: AgentBudget | None = None,
    ) -> AgentRunState:
        _validate_run_id(run_id)
        self._append(
            run_id,
            "run_created",
            _RunCreated(budgets=budgets or AgentBudget()).model_dump(mode="json"),
            idempotency_key="run_created",
        )
        return self.load(run_id)

    def attach_scene(
        self,
        run_id: str,
        preview: ScenePackagePreview,
        *,
        expected_archive_sha256: str | None = None,
    ) -> AgentRunState:
        if (
            expected_archive_sha256 is not None
            and preview.archive_sha256 != expected_archive_sha256
        ):
            raise AgentRuntimeError("Scene package archive hash does not match the expected input")
        state = self.load(run_id)
        if state.stage != "awaiting_scene":
            if state.scene and state.scene.archive_sha256 == preview.archive_sha256:
                return state
            raise AgentRuntimeError(f"Scene cannot be attached while run is {state.stage}")
        attachment = SceneAttachment(
            package=preview.package,
            archive_sha256=preview.archive_sha256,
            artifacts=preview.artifacts,
            digital_twin=preview.digital_twin,
        )
        self._append(
            run_id,
            "scene_attached",
            attachment.model_dump(mode="json"),
            idempotency_key=f"scene_attached:{preview.archive_sha256}",
        )
        return self.load(run_id)

    def start_scene_session(
        self,
        run_id: str,
        draft: SceneSessionDraft,
        *,
        action_id: str,
    ) -> AgentRunState:
        state = self.load(run_id)
        if (
            state.scene_sessions
            and state.scene_sessions[-1].draft.draft_sha256 == draft.draft_sha256
        ):
            return state
        try:
            session = build_scene_session(state, draft, action_id=action_id)
        except ValueError as exc:
            raise AgentRuntimeError(str(exc)) from exc
        self._append(
            run_id,
            "scene_session_started",
            _SceneSessionStarted(session=session).model_dump(mode="json"),
            idempotency_key=f"scene_session_started:{action_id}",
        )
        return self.load(run_id)

    def record_scene_candidate_evaluation(
        self, run_id: str, record: SceneCandidateEvaluationRecord, *, action_id: str
    ) -> AgentRunState:
        self._append(
            run_id,
            "scene_candidate_evaluated",
            _SceneCandidateEvaluated(record=record).model_dump(mode="json"),
            idempotency_key=f"scene_candidate_evaluated:{action_id}",
        )
        return self.load(run_id)

    def record_scene_candidate_adoption(
        self, run_id: str, record: SceneCandidateAdoptionRecord, *, action_id: str
    ) -> AgentRunState:
        self._append(
            run_id,
            "scene_candidate_adopted",
            _SceneCandidateAdopted(record=record).model_dump(mode="json"),
            idempotency_key=f"scene_candidate_adopted:{action_id}",
        )
        return self.load(run_id)

    def record_scene_variant_publication(
        self, run_id: str, record: SceneVariantPublishRecord, *, action_id: str
    ) -> AgentRunState:
        self._append(
            run_id,
            "scene_variant_published",
            _SceneVariantPublished(record=record).model_dump(mode="json"),
            idempotency_key=f"scene_variant_published:{action_id}",
        )
        return self.load(run_id)

    def record_scene_variant_review(
        self, run_id: str, record: SceneVariantReviewRecord, *, action_id: str
    ) -> AgentRunState:
        self._append(
            run_id,
            "scene_variant_reviewed",
            _SceneVariantReviewed(record=record).model_dump(mode="json"),
            idempotency_key=f"scene_variant_reviewed:{action_id}",
        )
        return self.load(run_id)

    def request_route_approval(
        self,
        run_id: str,
        decision_id: str,
        summary: str,
        *,
        fingerprint: str | None = None,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.stage != "route_ready":
            raise AgentRuntimeError(f"Approval cannot be requested while run is {state.stage}")
        decision = PendingDecision(
            decision_id=decision_id,
            summary=summary,
            fingerprint=fingerprint,
        )
        self._append(
            run_id,
            "approval_requested",
            _ApprovalRequested(decision=decision).model_dump(mode="json"),
            idempotency_key=f"approval_requested:{decision_id}",
        )
        return self.load(run_id)

    def propose_route(self, run_id: str, decision: RouteDecision) -> AgentRunState:
        state = self.load(run_id)
        if state.stage != "route_ready" or state.scene is None:
            raise AgentRuntimeError(f"Route cannot be proposed while run is {state.stage}")
        if decision.scene_package_id != state.scene.package.package_id:
            raise AgentRuntimeError("Route decision references a different Scene Package")
        if decision.scene_package_sha256 != state.scene.archive_sha256:
            raise AgentRuntimeError("Route decision references a different Scene Package content hash")
        self._append(
            run_id,
            "route_proposed",
            _RouteProposed(decision=decision).model_dump(mode="json"),
            idempotency_key=f"route_proposed:{decision.decision_id}:{decision.approval_fingerprint()}",
        )
        return self.load(run_id)

    def record_comparison_plan(self, run_id: str, plan: object) -> AgentRunState:
        from .comparison import ProviderComparisonPlan

        validated = ProviderComparisonPlan.model_validate(plan)
        state = self.load(run_id)
        if state.scene is None or state.stage != "route_ready":
            if state.comparison_plan == validated.model_dump(mode="json"):
                return state
            raise AgentRuntimeError(
                f"Comparison cannot be planned while run is {state.stage}"
            )
        if validated.comparison_id != run_id:
            raise AgentRuntimeError("Comparison plan ID must equal its coordinator run ID")
        if (
            validated.scene_package_id != state.scene.package.package_id
            or validated.scene_package_sha256 != state.scene.archive_sha256
        ):
            raise AgentRuntimeError("Comparison plan references a different Scene Package")
        self._append(
            run_id,
            "comparison_planned",
            _ComparisonPayload(value=validated.model_dump(mode="json")).model_dump(
                mode="json"
            ),
            idempotency_key=f"comparison_planned:{validated.approval_binding()}",
        )
        return self.load(run_id)

    def record_comparison_authorization(
        self, run_id: str, authorization: object
    ) -> AgentRunState:
        from .comparison import ComparisonAuthorizationDecision, ProviderComparisonPlan

        validated = ComparisonAuthorizationDecision.model_validate(authorization)
        state = self.load(run_id)
        if state.comparison_plan is None:
            raise AgentRuntimeError("Comparison authorization requires a persisted plan")
        plan = ProviderComparisonPlan.model_validate(state.comparison_plan)
        if state.comparison_authorization == validated.model_dump(mode="json"):
            return state
        if state.stage != "awaiting_approval":
            raise AgentRuntimeError(
                f"Comparison authorization is illegal while run is {state.stage}"
            )
        if (
            validated.dossier_id != plan.dossier_id
            or validated.dossier_sha256 != plan.dossier_sha256
            or validated.comparison_binding_sha256 != plan.approval_binding()
            or set(validated.authorized_action_ids)
            != {child.action_id for child in plan.children if child.role == "hosted"}
        ):
            raise AgentRuntimeError("Comparison authorization does not match the pending plan")
        self._append(
            run_id,
            "comparison_authorized",
            _ComparisonPayload(value=validated.model_dump(mode="json")).model_dump(
                mode="json"
            ),
            idempotency_key=f"comparison_authorized:{plan.approval_binding()}",
        )
        return self.load(run_id)

    def record_comparison_manifest(self, run_id: str, manifest: object) -> AgentRunState:
        from .comparison import ProviderComparisonManifest, ProviderComparisonPlan

        validated = ProviderComparisonManifest.model_validate(manifest)
        state = self.load(run_id)
        if state.comparison_plan is None or state.comparison_authorization is None:
            raise AgentRuntimeError("Comparison result requires persisted human authorization")
        plan = ProviderComparisonPlan.model_validate(state.comparison_plan)
        if state.comparison_manifest == validated.model_dump(mode="json"):
            return state
        if (
            validated.comparison_id != plan.comparison_id
            or validated.comparison_binding_sha256 != plan.approval_binding()
            or validated.scene_package_sha256 != plan.scene_package_sha256
        ):
            raise AgentRuntimeError("Comparison manifest does not match the authorized plan")
        self._append(
            run_id,
            "comparison_manifest_recorded",
            _ComparisonPayload(value=validated.model_dump(mode="json")).model_dump(
                mode="json"
            ),
            idempotency_key=(
                f"comparison_manifest_recorded:{validated.comparison_binding_sha256}:"
                f"{hashlib.sha256(_canonical_json(validated.model_dump(mode='json')).encode()).hexdigest()}"
            ),
        )
        return self.load(run_id)

    def assert_route_authorized(self, run_id: str, decision: RouteDecision) -> None:
        state = self.load(run_id)
        if state.stage != "approved" or state.route_decision is None:
            raise AgentRuntimeError("Provider execution requires an approved persisted route")
        if state.route_decision.decision_id != decision.decision_id:
            raise AgentRuntimeError("Approved route decision ID does not match execution intent")
        if state.route_decision.approval_fingerprint() != decision.approval_fingerprint():
            raise AgentRuntimeError("Approved route fingerprint does not match execution intent")

    def record_capability_attestation(
        self,
        run_id: str,
        attestation: CapabilityAttestation,
    ) -> AgentRunState:
        state = self.load(run_id)
        try:
            attestation.verify_fingerprint()
        except ValueError as exc:
            raise AgentRuntimeError(str(exc)) from exc
        if state.stage not in {"route_ready", "awaiting_approval", "approved"}:
            raise AgentRuntimeError(f"Capability cannot be attested while run is {state.stage}")
        if any(
            item.environment_sha256 == attestation.environment_sha256
            for item in state.capability_attestations
        ):
            return state
        if state.route_decision is not None and (
            attestation.provider_id != state.route_decision.selected.provider_id
            or attestation.model_id != state.route_decision.selected.model_id
        ):
            raise AgentRuntimeError("Attestation does not match the selected provider route")
        self._append(
            run_id,
            "capability_attested",
            _CapabilityAttested(attestation=attestation).model_dump(mode="json"),
            idempotency_key=f"capability_attested:{attestation.environment_sha256}",
        )
        return self.load(run_id)

    def resolve_route_approval(
        self,
        run_id: str,
        decision_id: str,
        resolution: Literal["approved", "rejected"],
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.stage != "awaiting_approval":
            raise AgentRuntimeError(f"Approval cannot be resolved while run is {state.stage}")
        if not any(item.decision_id == decision_id for item in state.pending_decisions):
            raise AgentRuntimeError(f"Unknown pending decision: {decision_id}")
        pending = next(
            item for item in state.pending_decisions if item.decision_id == decision_id
        )
        if pending.kind != "route_approval":
            raise AgentRuntimeError(
                "Comparison authorization requires the dedicated human-owner endpoint"
            )
        payload = _ApprovalResolved(decision_id=decision_id, resolution=resolution)
        self._append(
            run_id,
            "approval_resolved",
            payload.model_dump(mode="json"),
            idempotency_key=f"approval_resolved:{decision_id}:{resolution}",
        )
        return self.load(run_id)

    def reserve_provider_execution(
        self,
        run_id: str,
        execution_id: str,
        idempotency_key: str,
        decision: RouteDecision,
    ) -> AgentRunState:
        state = self.load(run_id)
        existing = next(
            (
                item
                for item in state.provider_executions
                if item.idempotency_key == idempotency_key
            ),
            None,
        )
        if existing is not None:
            if (
                existing.execution_id != execution_id
                or existing.route_fingerprint != decision.approval_fingerprint()
            ):
                raise AgentRuntimeError(
                    "Provider idempotency key is already bound to another execution intent"
                )
            return state
        self.assert_route_authorized(run_id, decision)
        matching_attestations = [
            item
            for item in state.capability_attestations
            if item.provider_id == decision.selected.provider_id
            and item.model_id == decision.selected.model_id
            and item.status == "supported"
        ]
        if not matching_attestations:
            raise AgentRuntimeError(
                "Provider execution requires a matching supported capability attestation"
            )
        if any(item.status not in {"succeeded", "failed", "cancelled"} for item in state.provider_executions):
            raise AgentRuntimeError("Another provider execution is still non-terminal")
        execution = ProviderExecutionLedgerEntry(
            execution_id=execution_id,
            idempotency_key=idempotency_key,
            route_decision_id=decision.decision_id,
            route_fingerprint=decision.approval_fingerprint(),
            attestation_environment_sha256=matching_attestations[-1].environment_sha256,
            provider_id=decision.selected.provider_id,
            model_id=decision.selected.model_id,
            status="reserved",
        )
        self._append(
            run_id,
            "provider_execution_reserved",
            _ProviderExecutionReserved(execution=execution).model_dump(mode="json"),
            idempotency_key=f"provider_execution_reserved:{idempotency_key}",
        )
        return self.load(run_id)

    def record_provider_submission(
        self,
        run_id: str,
        execution_id: str,
        provider_request_id: str,
    ) -> AgentRunState:
        state = self.load(run_id)
        execution = _find_execution(state, execution_id)
        if execution.provider_request_id is not None:
            if execution.provider_request_id != provider_request_id:
                raise AgentRuntimeError("Execution is already bound to another provider request")
            return state
        if execution.status != "reserved":
            raise AgentRuntimeError(f"Submission is illegal while execution is {execution.status}")
        payload = _ProviderExecutionSubmitted(
            execution_id=execution_id,
            provider_request_id=provider_request_id,
        )
        self._append(
            run_id,
            "provider_execution_submitted",
            payload.model_dump(mode="json"),
            idempotency_key=f"provider_execution_submitted:{execution_id}",
        )
        return self.load(run_id)

    def mark_provider_completion_unknown(
        self,
        run_id: str,
        execution_id: str,
        reason: str,
    ) -> AgentRunState:
        state = self.load(run_id)
        execution = _find_execution(state, execution_id)
        if execution.status == "completion_unknown":
            return state
        if execution.status not in {"reserved", "submitted"}:
            raise AgentRuntimeError(
                f"Unknown completion is illegal while execution is {execution.status}"
            )
        payload = _ProviderCompletionUnknown(execution_id=execution_id, reason=reason)
        self._append(
            run_id,
            "provider_completion_unknown",
            payload.model_dump(mode="json"),
            idempotency_key=f"provider_completion_unknown:{execution_id}",
        )
        return self.load(run_id)

    def record_provider_receipt(
        self,
        run_id: str,
        receipt: ProviderExecutionReceipt,
    ) -> AgentRunState:
        state = self.load(run_id)
        execution = _find_execution(state, receipt.execution_id)
        if execution.receipt is not None:
            if execution.receipt != receipt:
                raise AgentRuntimeError("Execution already has a different terminal receipt")
            return state
        if execution.status not in {"submitted", "completion_unknown"}:
            raise AgentRuntimeError(f"Receipt is illegal while execution is {execution.status}")
        if receipt.route_decision_id != execution.route_decision_id:
            raise AgentRuntimeError("Receipt route decision does not match the execution ledger")
        if receipt.route_fingerprint != execution.route_fingerprint:
            raise AgentRuntimeError("Receipt route fingerprint does not match the execution ledger")
        if receipt.provider_id != execution.provider_id or receipt.model_id != execution.model_id:
            raise AgentRuntimeError("Receipt provider identity does not match the execution ledger")
        if receipt.provider_request_id != execution.provider_request_id:
            raise AgentRuntimeError("Receipt provider request ID does not match the execution ledger")
        self._append(
            run_id,
            "provider_receipt_recorded",
            _ProviderReceiptRecorded(receipt=receipt).model_dump(mode="json"),
            idempotency_key=f"provider_receipt_recorded:{receipt.execution_id}",
        )
        return self.load(run_id)

    def record_codex_image_candidate(
        self,
        run_id: str,
        record: CodexImageCandidateRecord,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.scene is None or state.stage != "execution_succeeded":
            raise AgentRuntimeError(
                f"Codex image candidate is illegal while run is {state.stage}"
            )
        request = record.request
        beauty = next(
            (item for item in state.scene.package.passes if item.kind == "beauty"),
            None,
        )
        if beauty is None or (
            request.scene_package_id != state.scene.package.package_id
            or request.scene_package_sha256 != state.scene.archive_sha256
            or request.beauty_sha256 != beauty.artifact.sha256
        ):
            raise AgentRuntimeError(
                "Codex image request does not match the attached Scene Package beauty"
            )
        existing = next(
            (
                item
                for item in state.codex_image_candidates
                if item.receipt.candidate_id == record.receipt.candidate_id
            ),
            None,
        )
        if existing is not None:
            if existing != record:
                raise AgentRuntimeError("Codex candidate ID already has different evidence")
            return state
        self._append(
            run_id,
            "codex_image_candidate_recorded",
            _CodexImageCandidateRecorded(record=record).model_dump(mode="json"),
            idempotency_key=(
                f"codex_image_candidate_recorded:{record.receipt.candidate_id}"
            ),
        )
        return self.load(run_id)

    def record_tribunal_report(
        self,
        run_id: str,
        report: TribunalReport,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.tribunal_report is not None:
            if state.tribunal_report != report:
                raise AgentRuntimeError("Run already has a different tribunal report")
            return state
        _verify_tribunal_identity(state, report)
        self._append(
            run_id,
            "tribunal_report_recorded",
            _TribunalReportRecorded(report=report).model_dump(mode="json"),
            idempotency_key=f"tribunal_report_recorded:{report.dossier_sha256}",
        )
        return self.load(run_id)

    def record_negative_control(
        self,
        run_id: str,
        record: NegativeControlRecord,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.scene is None or state.stage != "execution_succeeded":
            raise AgentRuntimeError(
                f"Negative control is illegal while run is {state.stage}"
            )
        beauty = next(
            (item for item in state.scene.package.passes if item.kind == "beauty"),
            None,
        )
        if beauty is None or (
            record.request.scene_package_id != state.scene.package.package_id
            or record.request.scene_package_sha256 != state.scene.archive_sha256
            or record.request.beauty_sha256 != beauty.artifact.sha256
        ):
            raise AgentRuntimeError("Negative-control source binding does not match the run")
        existing = next(
            (
                item
                for item in state.negative_controls
                if item.receipt.control_id == record.receipt.control_id
            ),
            None,
        )
        if existing is not None:
            if existing != record:
                raise AgentRuntimeError("Negative-control ID already has different evidence")
            return state
        self._append(
            run_id,
            "negative_control_recorded",
            _NegativeControlRecorded(record=record).model_dump(mode="json"),
            idempotency_key=f"negative_control_recorded:{record.receipt.control_id}",
        )
        return self.load(run_id)

    def record_multimodal_tribunal(
        self,
        run_id: str,
        report: MultimodalTribunalReport,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.multimodal_tribunal is not None:
            if state.multimodal_tribunal != report:
                raise AgentRuntimeError("Run already has a different multimodal tribunal")
            return state
        _verify_multimodal_tribunal_identity(state, report)
        self._append(
            run_id,
            "multimodal_tribunal_recorded",
            _MultimodalTribunalRecorded(report=report).model_dump(mode="json"),
            idempotency_key=f"multimodal_tribunal_recorded:{report.report_id}",
        )
        return self.load(run_id)

    def record_candidate_adoption(
        self,
        run_id: str,
        decision: CandidateAdoptionDecision,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.adoption_decision is not None:
            if state.adoption_decision != decision:
                raise AgentRuntimeError("Run already adopted a different candidate")
            return state
        _verify_adoption_identity(state, decision)
        self._append(
            run_id,
            "production_candidate_adopted",
            _ProductionCandidateAdopted(decision=decision).model_dump(mode="json"),
            idempotency_key=f"production_candidate_adopted:{decision.decision_id}",
        )
        return self.load(run_id)

    def record_bounded_revision_request(
        self,
        run_id: str,
        request: BoundedRevisionRequest,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.bounded_revision_request is not None:
            if state.bounded_revision_request != request:
                raise AgentRuntimeError("Run already has a different bounded revision request")
            return state
        _verify_revision_request_identity(state, request)
        self._append(
            run_id,
            "bounded_revision_requested",
            _BoundedRevisionRequested(request=request).model_dump(mode="json"),
            idempotency_key=f"bounded_revision_requested:{request.revision_id}",
        )
        return self.load(run_id)

    def record_bounded_revision_result(
        self,
        run_id: str,
        result: BoundedRevisionResult,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.bounded_revision_result is not None:
            if state.bounded_revision_result != result:
                raise AgentRuntimeError("Run already has a different bounded revision result")
            return state
        if state.bounded_revision_request is None:
            raise AgentRuntimeError("Bounded revision result requires a persisted request")
        _verify_revision_result_identity(state.bounded_revision_request, result)
        self._append(
            run_id,
            "bounded_revision_recorded",
            _BoundedRevisionRecorded(result=result).model_dump(mode="json"),
            idempotency_key=f"bounded_revision_recorded:{result.revision_id}",
        )
        return self.load(run_id)

    def record_bounded_revision_correction(
        self,
        run_id: str,
        result: BoundedRevisionResult,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.bounded_revision_request is None or state.bounded_revision_result is None:
            raise AgentRuntimeError("Revision correction requires a recorded first attempt")
        if result.attempt != state.bounded_revision_result.attempt + 1:
            if state.bounded_revision_result == result:
                return state
            raise AgentRuntimeError("Revision correction attempt is not contiguous")
        _verify_revision_result_identity(state.bounded_revision_request, result)
        if result.receipt.raw_artifact_sha256 != (
            state.bounded_revision_result.receipt.raw_artifact_sha256
        ):
            raise AgentRuntimeError("Revision correction must reuse the same raw tool output")
        self._append(
            run_id,
            "bounded_revision_corrected",
            _BoundedRevisionRecorded(result=result).model_dump(mode="json"),
            idempotency_key=(
                f"bounded_revision_corrected:{result.revision_id}:{result.attempt}"
            ),
        )
        return self.load(run_id)

    def record_recovery_scorecard(
        self,
        run_id: str,
        scorecard: RecoveryScorecard,
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.recovery_scorecard is not None:
            if state.recovery_scorecard != scorecard:
                raise AgentRuntimeError("Run already has a different recovery scorecard")
            return state
        if scorecard.passed_cases != scorecard.total_cases:
            raise AgentRuntimeError("Only a fully passing recovery scorecard may be recorded")
        self._append(
            run_id,
            "recovery_scorecard_recorded",
            _RecoveryScorecardRecorded(scorecard=scorecard).model_dump(mode="json"),
            idempotency_key=f"recovery_scorecard_recorded:{scorecard.fingerprint()}",
        )
        return self.load(run_id)

    def propose_memory(self, run_id: str, proposal: MemoryProposal) -> AgentRunState:
        state = self.load(run_id)
        existing = next(
            (
                record
                for record in state.memory_records
                if record.proposal.memory_id == proposal.memory_id
            ),
            None,
        )
        if existing is not None:
            if existing.proposal != proposal:
                raise AgentRuntimeError("Memory ID is already bound to another proposal")
            return state
        if state.scene is None or proposal.project_id != state.scene.package.package_id:
            raise AgentRuntimeError("Memory proposal does not match the active project")
        if proposal.source_run_id != run_id:
            raise AgentRuntimeError("Memory proposal must cite its own durable run")
        event_hashes = {event.event_hash for event in self.events(run_id)}
        if not set(proposal.source_event_hashes).issubset(event_hashes):
            raise AgentRuntimeError("Memory proposal cites a forged or missing source event")
        self._append(
            run_id,
            "memory_proposed",
            _MemoryProposed(proposal=proposal).model_dump(mode="json"),
            idempotency_key=f"memory_proposed:{proposal.memory_id}:{proposal.content_sha256}",
        )
        return self.load(run_id)

    def resolve_memory(self, run_id: str, memory_id: str) -> AgentRunState:
        state = self.load(run_id)
        record = _find_memory(state, memory_id)
        if record.status != "proposed":
            return state
        decision = decide_memory_policy(record.proposal, state.memory_records)
        event_type: AgentEventType = (
            "memory_activated" if decision.verdict == "activate" else "memory_rejected"
        )
        self._append(
            run_id,
            event_type,
            _MemoryResolved(memory_id=memory_id, decision=decision).model_dump(mode="json"),
            idempotency_key=f"{event_type}:{memory_id}:{decision.decision_id}",
        )
        return self.load(run_id)

    def record_memory_scorecard(
        self, run_id: str, scorecard: MemoryScorecard
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.memory_scorecard is not None:
            if state.memory_scorecard != scorecard:
                raise AgentRuntimeError("Run already has a different memory scorecard")
            return state
        if scorecard.passed_cases != scorecard.total_cases:
            raise AgentRuntimeError("Only a fully passing memory scorecard may be recorded")
        self._append(
            run_id,
            "memory_scorecard_recorded",
            _MemoryScorecardRecorded(scorecard=scorecard).model_dump(mode="json"),
            idempotency_key=f"memory_scorecard_recorded:{scorecard.fingerprint()}",
        )
        return self.load(run_id)

    def record_harness_scorecard(
        self, run_id: str, scorecard: HarnessScorecard
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.harness_scorecard is not None:
            if state.harness_scorecard != scorecard:
                raise AgentRuntimeError("Run already has a different Harness scorecard")
            return state
        if scorecard.run_id != run_id:
            raise AgentRuntimeError("Harness scorecard references another run")
        if scorecard.scorecard_sha256 != scorecard.expected_sha256():
            raise AgentRuntimeError("Harness scorecard content hash is invalid")
        if scorecard.passed_cases != scorecard.total_cases:
            raise AgentRuntimeError("Only a fully passing Harness scorecard may be recorded")
        self._append(
            run_id,
            "harness_scorecard_recorded",
            _HarnessScorecardRecorded(scorecard=scorecard).model_dump(mode="json"),
            idempotency_key=f"harness_scorecard_recorded:{scorecard.scorecard_sha256}",
        )
        return self.load(run_id)

    def record_verified_delivery(
        self, run_id: str, delivery: VerifiedDeliveryRecord
    ) -> AgentRunState:
        state = self.load(run_id)
        if state.verified_delivery is not None:
            if state.verified_delivery != delivery:
                raise AgentRuntimeError("Run already has a different verified delivery")
            return state
        if delivery.run_id != run_id:
            raise AgentRuntimeError("Verified delivery references another run")
        if delivery.delivery_sha256 != delivery.expected_sha256():
            raise AgentRuntimeError("Verified delivery content hash is invalid")
        if state.bounded_revision_result is None or state.harness_scorecard is None:
            raise AgentRuntimeError("Verified delivery requires revision and Harness evidence")
        if (
            delivery.return_receipt.source_sha256
            != state.bounded_revision_result.composite_artifact_sha256
        ):
            raise AgentRuntimeError("Unreal return does not bind the verified revision")
        self._append(
            run_id,
            "verified_delivery_recorded",
            _VerifiedDeliveryRecorded(delivery=delivery).model_dump(mode="json"),
            idempotency_key=f"verified_delivery_recorded:{delivery.delivery_sha256}",
        )
        return self.load(run_id)

    def record_failure(self, run_id: str, code: str, detail: str) -> AgentRunState:
        state = self.load(run_id)
        if state.stage == "failed":
            raise AgentRuntimeError("A terminal failed run cannot accept more failures")
        payload = _FailureRecorded(code=code, detail=detail)
        self._append(
            run_id,
            "failure_recorded",
            payload.model_dump(mode="json"),
            idempotency_key=f"failure_recorded:{code}:{state.last_sequence + 1}",
        )
        return self.load(run_id)

    def begin_iteration(self, run_id: str, iteration_id: str) -> AgentRunState:
        payload = _IterationStarted(iteration_id=iteration_id)
        self._append(
            run_id,
            "iteration_started",
            payload.model_dump(mode="json"),
            idempotency_key=f"iteration_started:{iteration_id}",
        )
        return self.load(run_id)

    def start_tool_call(
        self,
        run_id: str,
        call_id: str,
        capability_id: str,
        input_sha256: str,
    ) -> AgentRunState:
        payload = _ToolCallStarted(
            call=PendingToolCall(
                call_id=call_id,
                capability_id=capability_id,
                input_sha256=input_sha256,
            )
        )
        self._append(
            run_id,
            "tool_call_started",
            payload.model_dump(mode="json"),
            idempotency_key=f"tool_call_started:{call_id}",
        )
        return self.load(run_id)

    def record_tool_observation(
        self,
        run_id: str,
        observation: ToolObservationRecord,
    ) -> AgentRunState:
        self._append(
            run_id,
            "tool_observed",
            _ToolObserved(observation=observation).model_dump(mode="json"),
            idempotency_key=f"tool_observed:{observation.call_id}",
        )
        return self.load(run_id)

    def load(self, run_id: str) -> AgentRunState:
        events = self.events(run_id)
        return reduce_agent_events(events)

    def events(self, run_id: str) -> list[AgentEvent]:
        _validate_run_id(run_id)
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT run_id, sequence, event_id, event_type, occurred_at,
                       idempotency_key, data_json, previous_hash, event_hash
                FROM agent_events
                WHERE run_id = ?
                ORDER BY sequence
                """,
                (run_id,),
            ).fetchall()
        if not rows:
            raise AgentRuntimeError(f"Unknown Agent run: {run_id}")
        events = _events_from_rows(rows)
        _verify_event_chain(events)
        return events

    def list_run_ids(self) -> list[str]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT run_id, MAX(sequence) AS last_sequence
                FROM agent_events
                GROUP BY run_id
                ORDER BY last_sequence DESC, run_id
                """
            ).fetchall()
        return [str(row[0]) for row in rows]

    def _append(
        self,
        run_id: str,
        event_type: AgentEventType,
        data: dict[str, Any],
        *,
        idempotency_key: str,
    ) -> AgentEvent:
        _validate_run_id(run_id)
        data_json = _canonical_json(data)
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    """
                    SELECT run_id, sequence, event_id, event_type, occurred_at,
                           idempotency_key, data_json, previous_hash, event_hash
                    FROM agent_events
                    WHERE run_id = ? AND idempotency_key = ?
                    """,
                    (run_id, idempotency_key),
                ).fetchone()
                if existing is not None:
                    if existing[3] != event_type or existing[6] != data_json:
                        raise AgentRuntimeError(
                            "Idempotency key was already used for a different Agent event"
                        )
                    connection.commit()
                    return _event_from_row(existing)

                history_rows = connection.execute(
                    """
                    SELECT run_id, sequence, event_id, event_type, occurred_at,
                           idempotency_key, data_json, previous_hash, event_hash
                    FROM agent_events
                    WHERE run_id = ? ORDER BY sequence
                    """,
                    (run_id,),
                ).fetchall()
                history = _events_from_rows(history_rows)
                if history:
                    _verify_event_chain(history)
                sequence = len(history) + 1
                previous_hash = history[-1].event_hash if history else None
                occurred_at = datetime.now(UTC).isoformat()
                event_id = f"event-{uuid.uuid4().hex}"
                event_hash = _event_hash(
                    run_id=run_id,
                    sequence=sequence,
                    event_id=event_id,
                    event_type=event_type,
                    occurred_at=occurred_at,
                    idempotency_key=idempotency_key,
                    data_json=data_json,
                    previous_hash=previous_hash,
                )
                candidate = AgentEvent(
                    run_id=run_id,
                    sequence=sequence,
                    event_id=event_id,
                    event_type=event_type,
                    occurred_at=occurred_at,
                    idempotency_key=idempotency_key,
                    data=data,
                    previous_hash=previous_hash,
                    event_hash=event_hash,
                )
                # Validate the transition while holding the write lock. This closes the race where
                # two callers both observe the same state before appending incompatible events.
                reduce_agent_events([*history, candidate])
                connection.execute(
                    """
                    INSERT INTO agent_events (
                        run_id, sequence, event_id, event_type, occurred_at,
                        idempotency_key, data_json, previous_hash, event_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        sequence,
                        event_id,
                        event_type,
                        occurred_at,
                        idempotency_key,
                        data_json,
                        previous_hash,
                        event_hash,
                    ),
                )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        return candidate

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


def reduce_agent_events(events: list[AgentEvent]) -> AgentRunState:
    if not events or events[0].event_type != "run_created":
        raise AgentRuntimeError("Agent event history must begin with run_created")
    created = _RunCreated.model_validate(events[0].data)
    state = AgentRunState(
        run_id=events[0].run_id,
        stage="awaiting_scene",
        created_at=events[0].occurred_at,
        budgets=created.budgets,
        last_sequence=events[0].sequence,
    )
    for event in events[1:]:
        if event.run_id != state.run_id:
            raise AgentRuntimeError("Agent event history mixes run identities")
        if event.event_type == "run_created":
            raise AgentRuntimeError("run_created may only be the first Agent event")
        if event.event_type == "scene_attached":
            if state.stage != "awaiting_scene":
                raise AgentRuntimeError(f"scene_attached is illegal while run is {state.stage}")
            state.scene = SceneAttachment.model_validate(event.data)
            state.stage = "route_ready"
        elif event.event_type == "scene_session_started":
            if state.scene is None:
                raise AgentRuntimeError("scene_session_started requires an attached Scene Package")
            session = _SceneSessionStarted.model_validate(event.data).session
            if session.run_id != state.run_id:
                raise AgentRuntimeError("scene_session_started references another run")
            if session.scene_package_sha256 != state.scene.archive_sha256:
                raise AgentRuntimeError(
                    "scene_session_started references different Scene Package content"
                )
            if session.draft.basis_sequence != event.sequence - 1:
                raise AgentRuntimeError("scene_session_started draft is stale")
            try:
                validate_scene_session_draft(state, session.draft)
            except ValueError as exc:
                raise AgentRuntimeError(str(exc)) from exc
            previous = state.scene_sessions[-1] if state.scene_sessions else None
            expected_previous = previous.session_id if previous else None
            if session.supersedes_session_id != expected_previous:
                raise AgentRuntimeError("scene_session_started supersession chain is invalid")
            if any(item.session_id == session.session_id for item in state.scene_sessions):
                raise AgentRuntimeError("scene_session_started duplicates a persisted session")
            state.scene_sessions.append(session)
        elif event.event_type == "scene_candidate_evaluated":
            if state.scene is None or not state.scene_sessions:
                raise AgentRuntimeError("scene candidate evaluation requires a Scene Session")
            if state.scene_candidate_evaluation is not None:
                raise AgentRuntimeError("scene candidate evaluation is already persisted")
            record = _SceneCandidateEvaluated.model_validate(event.data).record
            try:
                validate_session_binding(
                    record,
                    run_id=state.run_id,
                    scene_package_sha256=state.scene.archive_sha256,
                    session=state.scene_sessions[-1],
                )
            except ValueError as exc:
                raise AgentRuntimeError(str(exc)) from exc
            state.scene_candidate_evaluation = record
        elif event.event_type == "scene_candidate_adopted":
            evaluation = state.scene_candidate_evaluation
            if evaluation is None:
                raise AgentRuntimeError("scene candidate adoption requires persisted evaluation")
            if state.scene_candidate_adoption is not None:
                raise AgentRuntimeError("scene candidate adoption is already persisted")
            record = _SceneCandidateAdopted.model_validate(event.data).record
            decision = record.decision
            corrected = evaluation.corrected_evaluation
            corrected_plan = evaluation.corrected_plan
            if (
                decision.evaluation_sha256 != corrected.evaluation_sha256
                or decision.plan_sha256 != corrected_plan.plan_sha256
                or decision.candidate_scene != corrected.candidate_scene
            ):
                raise AgentRuntimeError("scene adoption references another evaluated candidate")
            state.scene_candidate_adoption = record
        elif event.event_type == "scene_variant_published":
            adoption = state.scene_candidate_adoption
            if adoption is None:
                raise AgentRuntimeError("scene publication requires persisted adoption")
            if state.scene_variant_publication is not None:
                raise AgentRuntimeError("scene variant publication is already persisted")
            record = _SceneVariantPublished.model_validate(event.data).record
            if record.request.decision != adoption.decision:
                raise AgentRuntimeError("scene publication references another adoption decision")
            state.scene_variant_publication = record
        elif event.event_type == "scene_variant_reviewed":
            publication = state.scene_variant_publication
            evaluation = state.scene_candidate_evaluation
            if publication is None or evaluation is None:
                raise AgentRuntimeError("scene review requires persisted evaluation and publication")
            if state.scene_variant_review is not None:
                raise AgentRuntimeError("scene variant review is already persisted")
            record = _SceneVariantReviewed.model_validate(event.data).record
            if (
                record.request.publish_request_sha256 != publication.request.request_sha256
                or record.request.decision_sha256
                != publication.request.decision.decision_sha256
            ):
                raise AgentRuntimeError("scene review references another published variant")
            expected = compile_scene_variant_lineage(
                failed=evaluation.failed_evaluation,
                corrected=evaluation.corrected_evaluation,
                publish_request=publication.request,
                publish_receipt=publication.receipt,
                review_request=record.request,
                review_receipt=record.receipt,
            )
            if record.lineage != expected:
                raise AgentRuntimeError("scene review lineage differs from persisted artifacts")
            state.scene_variant_review = record
        elif event.event_type == "approval_requested":
            if state.stage != "route_ready":
                raise AgentRuntimeError(
                    f"approval_requested is illegal while run is {state.stage}"
                )
            request = _ApprovalRequested.model_validate(event.data)
            state.pending_decisions.append(request.decision)
            state.approval = "pending"
            state.stage = "awaiting_approval"
        elif event.event_type == "approval_resolved":
            if state.stage != "awaiting_approval":
                raise AgentRuntimeError(
                    f"approval_resolved is illegal while run is {state.stage}"
                )
            resolution = _ApprovalResolved.model_validate(event.data)
            matches = [
                item for item in state.pending_decisions if item.decision_id == resolution.decision_id
            ]
            if len(matches) != 1:
                raise AgentRuntimeError(
                    f"approval_resolved references unknown decision {resolution.decision_id}"
                )
            if matches[0].kind != "route_approval":
                raise AgentRuntimeError(
                    "approval_resolved cannot resolve a comparison authorization"
                )
            state.pending_decisions = [
                item
                for item in state.pending_decisions
                if item.decision_id != resolution.decision_id
            ]
            state.approval = resolution.resolution
            state.stage = "approved" if resolution.resolution == "approved" else "route_ready"
        elif event.event_type == "failure_recorded":
            failure = _FailureRecorded.model_validate(event.data)
            state.failures.append(f"{failure.code}: {failure.detail}")
            state.stage = "failed"
        elif event.event_type == "iteration_started":
            if state.stage not in {"route_ready", "awaiting_approval", "approved"}:
                raise AgentRuntimeError(
                    f"iteration_started is illegal while run is {state.stage}"
                )
            _IterationStarted.model_validate(event.data)
            if state.budgets.used_iterations >= state.budgets.max_iterations:
                raise AgentRuntimeError("Agent iteration budget is exhausted")
            state.budgets.used_iterations += 1
        elif event.event_type == "tool_call_started":
            if state.stage not in {"route_ready", "awaiting_approval", "approved"}:
                raise AgentRuntimeError(
                    f"tool_call_started is illegal while run is {state.stage}"
                )
            started = _ToolCallStarted.model_validate(event.data)
            if state.budgets.used_tool_calls >= state.budgets.max_tool_calls:
                raise AgentRuntimeError("Agent tool-call budget is exhausted")
            if any(item.call_id == started.call.call_id for item in state.pending_tool_calls):
                raise AgentRuntimeError(f"Tool call is already pending: {started.call.call_id}")
            state.budgets.used_tool_calls += 1
            state.pending_tool_calls.append(started.call)
        elif event.event_type == "tool_observed":
            observed = _ToolObserved.model_validate(event.data).observation
            matching = [
                item for item in state.pending_tool_calls if item.call_id == observed.call_id
            ]
            if len(matching) != 1 or matching[0].capability_id != observed.capability_id:
                raise AgentRuntimeError(
                    f"tool_observed references unknown tool call {observed.call_id}"
                )
            state.pending_tool_calls = [
                item for item in state.pending_tool_calls if item.call_id != observed.call_id
            ]
            state.observations.append(observed)
        elif event.event_type == "route_proposed":
            if state.stage != "route_ready" or state.scene is None:
                raise AgentRuntimeError(f"route_proposed is illegal while run is {state.stage}")
            route = _RouteProposed.model_validate(event.data).decision
            if route.scene_package_id != state.scene.package.package_id:
                raise AgentRuntimeError("route_proposed references a different Scene Package")
            if route.scene_package_sha256 != state.scene.archive_sha256:
                raise AgentRuntimeError("route_proposed references different Scene Package content")
            state.route_decision = route
            if route.requires_explicit_approval:
                state.pending_decisions.append(
                    PendingDecision(
                        decision_id=route.decision_id,
                        summary=route.rationale,
                        fingerprint=route.approval_fingerprint(),
                    )
                )
                state.approval = "pending"
                state.stage = "awaiting_approval"
            else:
                state.approval = "approved"
                state.stage = "approved"
        elif event.event_type == "capability_attested":
            if state.stage not in {"route_ready", "awaiting_approval", "approved"}:
                raise AgentRuntimeError(
                    f"capability_attested is illegal while run is {state.stage}"
                )
            attestation = _CapabilityAttested.model_validate(event.data).attestation
            try:
                attestation.verify_fingerprint()
            except ValueError as exc:
                raise AgentRuntimeError(str(exc)) from exc
            if state.route_decision is not None and (
                attestation.provider_id != state.route_decision.selected.provider_id
                or attestation.model_id != state.route_decision.selected.model_id
            ):
                raise AgentRuntimeError("capability_attested does not match selected route")
            state.capability_attestations.append(attestation)
        elif event.event_type == "comparison_planned":
            from .comparison import ProviderComparisonPlan

            if state.stage != "route_ready" or state.scene is None:
                raise AgentRuntimeError(
                    f"comparison_planned is illegal while run is {state.stage}"
                )
            plan = ProviderComparisonPlan.model_validate(
                _ComparisonPayload.model_validate(event.data).value
            )
            if (
                plan.comparison_id != state.run_id
                or plan.scene_package_id != state.scene.package.package_id
                or plan.scene_package_sha256 != state.scene.archive_sha256
            ):
                raise AgentRuntimeError("comparison_planned identity does not match run")
            state.comparison_plan = plan.model_dump(mode="json")
            state.pending_decisions.append(
                PendingDecision(
                    decision_id=f"authorize-{plan.comparison_id}",
                    kind="comparison_authorization",
                    summary=(
                        "Authorize the hosted privacy/cost action for this exact "
                        "comparison fingerprint. Local project compute is not gated."
                    ),
                    fingerprint=plan.approval_binding(),
                )
            )
            state.approval = "pending"
            state.stage = "awaiting_approval"
        elif event.event_type == "comparison_authorized":
            from .comparison import (
                ComparisonAuthorizationDecision,
                ProviderComparisonPlan,
            )

            if state.stage != "awaiting_approval" or state.comparison_plan is None:
                raise AgentRuntimeError(
                    f"comparison_authorized is illegal while run is {state.stage}"
                )
            plan = ProviderComparisonPlan.model_validate(state.comparison_plan)
            authorization = ComparisonAuthorizationDecision.model_validate(
                _ComparisonPayload.model_validate(event.data).value
            )
            pending_id = f"authorize-{plan.comparison_id}"
            pending = [
                item
                for item in state.pending_decisions
                if item.decision_id == pending_id
                and item.kind == "comparison_authorization"
                and item.fingerprint == plan.approval_binding()
            ]
            if len(pending) != 1 or (
                authorization.dossier_id != plan.dossier_id
                or authorization.dossier_sha256 != plan.dossier_sha256
                or authorization.comparison_binding_sha256 != plan.approval_binding()
                or set(authorization.authorized_action_ids)
                != {child.action_id for child in plan.children if child.role == "hosted"}
            ):
                raise AgentRuntimeError(
                    "comparison_authorized does not match the pending comparison"
                )
            state.comparison_authorization = authorization.model_dump(mode="json")
            state.pending_decisions = [
                item for item in state.pending_decisions if item.decision_id != pending_id
            ]
            state.approval = "approved"
            state.stage = "approved"
        elif event.event_type == "comparison_manifest_recorded":
            from .comparison import ProviderComparisonManifest, ProviderComparisonPlan

            if state.comparison_plan is None or state.comparison_authorization is None:
                raise AgentRuntimeError(
                    "comparison_manifest_recorded requires human authorization"
                )
            plan = ProviderComparisonPlan.model_validate(state.comparison_plan)
            manifest = ProviderComparisonManifest.model_validate(
                _ComparisonPayload.model_validate(event.data).value
            )
            if (
                manifest.comparison_id != plan.comparison_id
                or manifest.comparison_binding_sha256 != plan.approval_binding()
                or manifest.scene_package_sha256 != plan.scene_package_sha256
            ):
                raise AgentRuntimeError(
                    "comparison_manifest_recorded identity does not match plan"
                )
            state.comparison_manifest = manifest.model_dump(mode="json")
            if manifest.status == "succeeded":
                state.stage = "execution_succeeded"
            elif manifest.status == "needs_human_recovery":
                state.stage = "reconciling"
            elif manifest.status == "failed":
                state.stage = "failed"
            else:
                state.stage = "executing"
        elif event.event_type == "provider_execution_reserved":
            reserved = _ProviderExecutionReserved.model_validate(event.data).execution
            if state.stage != "approved" or state.route_decision is None:
                raise AgentRuntimeError(
                    f"provider_execution_reserved is illegal while run is {state.stage}"
                )
            if reserved.route_decision_id != state.route_decision.decision_id or (
                reserved.route_fingerprint != state.route_decision.approval_fingerprint()
            ):
                raise AgentRuntimeError("Reserved execution does not match the approved route")
            attestations = [
                item
                for item in state.capability_attestations
                if item.environment_sha256 == reserved.attestation_environment_sha256
                and item.provider_id == reserved.provider_id
                and item.model_id == reserved.model_id
                and item.status == "supported"
            ]
            if len(attestations) != 1:
                raise AgentRuntimeError(
                    "Reserved execution does not reference a supported capability attestation"
                )
            if any(
                item.status not in {"succeeded", "failed", "cancelled"}
                for item in state.provider_executions
            ):
                raise AgentRuntimeError("Only one provider execution may be non-terminal")
            state.provider_executions.append(reserved)
            state.stage = "executing"
        elif event.event_type == "provider_execution_submitted":
            submitted = _ProviderExecutionSubmitted.model_validate(event.data)
            execution = _find_execution(state, submitted.execution_id)
            if execution.status != "reserved" or state.stage != "executing":
                raise AgentRuntimeError(
                    f"provider_execution_submitted is illegal while execution is {execution.status}"
                )
            execution.provider_request_id = submitted.provider_request_id
            execution.status = "submitted"
        elif event.event_type == "provider_completion_unknown":
            unknown = _ProviderCompletionUnknown.model_validate(event.data)
            execution = _find_execution(state, unknown.execution_id)
            if execution.status not in {"reserved", "submitted"}:
                raise AgentRuntimeError(
                    f"provider_completion_unknown is illegal while execution is {execution.status}"
                )
            execution.status = "completion_unknown"
            execution.unknown_reason = unknown.reason
            state.stage = "reconciling"
        elif event.event_type == "provider_receipt_recorded":
            receipt = _ProviderReceiptRecorded.model_validate(event.data).receipt
            execution = _find_execution(state, receipt.execution_id)
            if execution.status not in {"submitted", "completion_unknown"}:
                raise AgentRuntimeError(
                    f"provider_receipt_recorded is illegal while execution is {execution.status}"
                )
            if (
                receipt.route_decision_id != execution.route_decision_id
                or receipt.route_fingerprint != execution.route_fingerprint
                or receipt.provider_id != execution.provider_id
                or receipt.model_id != execution.model_id
                or receipt.provider_request_id != execution.provider_request_id
            ):
                raise AgentRuntimeError("provider_receipt_recorded identity does not match ledger")
            execution.receipt = receipt
            execution.status = receipt.status
            execution.unknown_reason = None
            if receipt.status == "succeeded":
                state.stage = "execution_succeeded"
            else:
                state.stage = "failed"
                state.failures.append(
                    f"provider_{receipt.status}: {receipt.error_code or 'terminal outcome'}"
                )
        elif event.event_type == "codex_image_candidate_recorded":
            if state.scene is None or state.stage != "execution_succeeded":
                raise AgentRuntimeError(
                    "codex_image_candidate_recorded requires a successful source execution"
                )
            record = _CodexImageCandidateRecorded.model_validate(event.data).record
            beauty = next(
                (item for item in state.scene.package.passes if item.kind == "beauty"),
                None,
            )
            if beauty is None or (
                record.request.scene_package_id != state.scene.package.package_id
                or record.request.scene_package_sha256 != state.scene.archive_sha256
                or record.request.beauty_sha256 != beauty.artifact.sha256
            ):
                raise AgentRuntimeError(
                    "codex_image_candidate_recorded source binding does not match run"
                )
            if any(
                item.receipt.candidate_id == record.receipt.candidate_id
                for item in state.codex_image_candidates
            ):
                raise AgentRuntimeError("codex_image_candidate_recorded duplicates candidate ID")
            state.codex_image_candidates.append(record)
        elif event.event_type == "tribunal_report_recorded":
            if state.tribunal_report is not None:
                raise AgentRuntimeError("tribunal_report_recorded may occur only once")
            report = _TribunalReportRecorded.model_validate(event.data).report
            _verify_tribunal_identity(state, report)
            state.tribunal_report = report
        elif event.event_type == "negative_control_recorded":
            if state.scene is None or state.stage != "execution_succeeded":
                raise AgentRuntimeError(
                    "negative_control_recorded requires a successful matched run"
                )
            record = _NegativeControlRecorded.model_validate(event.data).record
            beauty = next(
                (item for item in state.scene.package.passes if item.kind == "beauty"),
                None,
            )
            if beauty is None or (
                record.request.scene_package_id != state.scene.package.package_id
                or record.request.scene_package_sha256 != state.scene.archive_sha256
                or record.request.beauty_sha256 != beauty.artifact.sha256
            ):
                raise AgentRuntimeError("negative_control_recorded source binding mismatch")
            if any(
                item.receipt.control_id == record.receipt.control_id
                for item in state.negative_controls
            ):
                raise AgentRuntimeError("negative_control_recorded duplicates control ID")
            state.negative_controls.append(record)
        elif event.event_type == "multimodal_tribunal_recorded":
            if state.multimodal_tribunal is not None:
                raise AgentRuntimeError("multimodal_tribunal_recorded may occur only once")
            report = _MultimodalTribunalRecorded.model_validate(event.data).report
            _verify_multimodal_tribunal_identity(state, report)
            state.multimodal_tribunal = report
        elif event.event_type == "production_candidate_adopted":
            if state.adoption_decision is not None:
                raise AgentRuntimeError("production_candidate_adopted may occur only once")
            decision = _ProductionCandidateAdopted.model_validate(event.data).decision
            _verify_adoption_identity(state, decision)
            state.adoption_decision = decision
        elif event.event_type == "bounded_revision_requested":
            if state.bounded_revision_request is not None:
                raise AgentRuntimeError("bounded_revision_requested may occur only once")
            request = _BoundedRevisionRequested.model_validate(event.data).request
            _verify_revision_request_identity(state, request)
            state.bounded_revision_request = request
        elif event.event_type == "bounded_revision_recorded":
            if state.bounded_revision_result is not None:
                raise AgentRuntimeError("bounded_revision_recorded may occur only once")
            if state.bounded_revision_request is None:
                raise AgentRuntimeError("bounded_revision_recorded requires a request")
            result = _BoundedRevisionRecorded.model_validate(event.data).result
            _verify_revision_result_identity(state.bounded_revision_request, result)
            state.bounded_revision_result = result
            state.bounded_revision_attempts.append(result)
        elif event.event_type == "bounded_revision_corrected":
            if state.bounded_revision_request is None or state.bounded_revision_result is None:
                raise AgentRuntimeError("bounded_revision_corrected requires a first attempt")
            result = _BoundedRevisionRecorded.model_validate(event.data).result
            _verify_revision_result_identity(state.bounded_revision_request, result)
            if result.attempt != state.bounded_revision_result.attempt + 1 or (
                result.receipt.raw_artifact_sha256
                != state.bounded_revision_result.receipt.raw_artifact_sha256
            ):
                raise AgentRuntimeError("bounded_revision_corrected lineage is invalid")
            state.bounded_revision_result = result
            state.bounded_revision_attempts.append(result)
        elif event.event_type == "recovery_scorecard_recorded":
            if state.recovery_scorecard is not None:
                raise AgentRuntimeError("recovery_scorecard_recorded may occur only once")
            scorecard = _RecoveryScorecardRecorded.model_validate(event.data).scorecard
            if scorecard.passed_cases != scorecard.total_cases:
                raise AgentRuntimeError("Persisted recovery scorecard is not fully passing")
            state.recovery_scorecard = scorecard
        elif event.event_type == "memory_proposed":
            proposal = _MemoryProposed.model_validate(event.data).proposal
            if any(
                record.proposal.memory_id == proposal.memory_id
                for record in state.memory_records
            ):
                raise AgentRuntimeError("memory_proposed duplicates a memory ID")
            state.memory_records.append(MemoryRecord(proposal=proposal, status="proposed"))
        elif event.event_type in {"memory_activated", "memory_rejected"}:
            payload = _MemoryResolved.model_validate(event.data)
            record = _find_memory(state, payload.memory_id)
            if record.status != "proposed":
                raise AgentRuntimeError("Memory may be resolved only once")
            expected = decide_memory_policy(record.proposal, state.memory_records)
            if payload.decision != expected:
                raise AgentRuntimeError("Persisted memory policy decision does not replay")
            expected_type = (
                "memory_activated"
                if payload.decision.verdict == "activate"
                else "memory_rejected"
            )
            if event.event_type != expected_type:
                raise AgentRuntimeError("Memory event conflicts with its policy decision")
            record.status = (
                "active" if payload.decision.verdict == "activate" else "rejected"
            )
            record.policy_decision = payload.decision
            if payload.decision.superseded_memory_id:
                previous = _find_memory(
                    state, payload.decision.superseded_memory_id
                )
                if previous.status != "active":
                    raise AgentRuntimeError("Superseded memory is not active")
                previous.status = "superseded"
                previous.superseded_by_memory_id = payload.memory_id
        elif event.event_type == "memory_scorecard_recorded":
            if state.memory_scorecard is not None:
                raise AgentRuntimeError("memory_scorecard_recorded may occur only once")
            scorecard = _MemoryScorecardRecorded.model_validate(event.data).scorecard
            if scorecard.passed_cases != scorecard.total_cases:
                raise AgentRuntimeError("Persisted memory scorecard is not fully passing")
            state.memory_scorecard = scorecard
        elif event.event_type == "harness_scorecard_recorded":
            if state.harness_scorecard is not None:
                raise AgentRuntimeError("harness_scorecard_recorded may occur only once")
            scorecard = _HarnessScorecardRecorded.model_validate(event.data).scorecard
            if scorecard.run_id != state.run_id:
                raise AgentRuntimeError("Persisted Harness scorecard references another run")
            if scorecard.scorecard_sha256 != scorecard.expected_sha256():
                raise AgentRuntimeError("Persisted Harness scorecard hash is invalid")
            if scorecard.passed_cases != scorecard.total_cases:
                raise AgentRuntimeError("Persisted Harness scorecard is not fully passing")
            state.harness_scorecard = scorecard
        elif event.event_type == "verified_delivery_recorded":
            if state.verified_delivery is not None:
                raise AgentRuntimeError("verified_delivery_recorded may occur only once")
            delivery = _VerifiedDeliveryRecorded.model_validate(event.data).delivery
            if delivery.run_id != state.run_id:
                raise AgentRuntimeError("Persisted delivery references another run")
            if delivery.delivery_sha256 != delivery.expected_sha256():
                raise AgentRuntimeError("Persisted delivery hash is invalid")
            if state.bounded_revision_result is None or state.harness_scorecard is None:
                raise AgentRuntimeError("Persisted delivery is missing prerequisite evidence")
            if (
                delivery.return_receipt.source_sha256
                != state.bounded_revision_result.composite_artifact_sha256
            ):
                raise AgentRuntimeError("Persisted delivery references another revision")
            state.verified_delivery = delivery
        state.last_sequence = event.sequence
    return state


def _find_memory(state: AgentRunState, memory_id: str) -> MemoryRecord:
    matches = [
        record
        for record in state.memory_records
        if record.proposal.memory_id == memory_id
    ]
    if len(matches) != 1:
        raise AgentRuntimeError(f"Unknown memory record: {memory_id}")
    return matches[0]


def _verify_tribunal_identity(state: AgentRunState, report: TribunalReport) -> None:
    if state.scene is None or state.stage != "execution_succeeded":
        raise AgentRuntimeError("Tribunal report requires a successful matched-candidate run")
    if len(state.provider_executions) != 1 or not state.codex_image_candidates:
        raise AgentRuntimeError("Tribunal report requires both real candidate receipts")
    local = state.provider_executions[0]
    codex = state.codex_image_candidates[-1]
    if local.receipt is None or not local.receipt.artifacts:
        raise AgentRuntimeError("Tribunal report requires the local candidate receipt")
    dossier = report.dossier
    by_role = {item.role: item for item in dossier.artifacts}
    beauty = next(
        (item for item in state.scene.package.passes if item.kind == "beauty"),
        None,
    )
    if beauty is None:
        raise AgentRuntimeError("Tribunal report requires the verified beauty evidence")
    if (
        dossier.scene_package_id != state.scene.package.package_id
        or dossier.scene_package_sha256 != state.scene.archive_sha256
        or dossier.beauty_sha256 != beauty.artifact.sha256
        or by_role["source"].artifact_sha256 != beauty.artifact.sha256
        or by_role["source"].receipt_binding_sha256 != state.scene.archive_sha256
        or by_role["local_comfy"].artifact_sha256 != local.receipt.artifacts[0].sha256
        or by_role["local_comfy"].receipt_binding_sha256 != local.route_fingerprint
        or by_role["codex_image"].artifact_sha256 != codex.receipt.artifact.sha256
        or by_role["codex_image"].receipt_binding_sha256
        != codex.receipt.request_binding_sha256
    ):
        raise AgentRuntimeError("Tribunal dossier does not match durable run evidence")


def _verify_multimodal_tribunal_identity(
    state: AgentRunState,
    report: MultimodalTribunalReport,
) -> None:
    from .tribunal import report_fingerprint

    if state.tribunal_report is None or not state.negative_controls:
        raise AgentRuntimeError(
            "Multimodal tribunal requires the base tribunal and negative control"
        )
    negative = state.negative_controls[-1]
    if (
        report.base_tribunal_sha256 != report_fingerprint(state.tribunal_report)
        or report.negative_control != negative
    ):
        raise AgentRuntimeError("Multimodal tribunal does not match durable base evidence")
    results_by_role = {
        item.candidate_role: item for item in state.tribunal_report.results
    }
    expected_inputs = {
        "source": state.tribunal_report.dossier.beauty_sha256,
        "local_comfy": results_by_role["local_comfy"].artifact_sha256,
        "codex_image": results_by_role["codex_image"].artifact_sha256,
        "negative_control": negative.receipt.artifact.sha256,
    }
    actual_inputs = {item.role: item.artifact_sha256 for item in report.critic.inputs}
    if actual_inputs != expected_inputs:
        raise AgentRuntimeError("Multimodal critic inputs do not match durable artifacts")


def _verify_adoption_identity(
    state: AgentRunState,
    decision: CandidateAdoptionDecision,
) -> None:
    from .tribunal import report_fingerprint

    if state.tribunal_report is None or state.multimodal_tribunal is None:
        raise AgentRuntimeError("Candidate adoption requires both persisted tribunals")
    if decision.evidence.base_tribunal_sha256 != report_fingerprint(
        state.tribunal_report
    ) or decision.evidence.multimodal_tribunal_sha256 != (
        state.multimodal_tribunal.fingerprint()
    ):
        raise AgentRuntimeError("Candidate adoption evidence fingerprints do not match")
    result = next(
        (
            item
            for item in state.tribunal_report.results
            if item.candidate_role == decision.selected_role
        ),
        None,
    )
    if result is None or not result.eligible or (
        result.artifact_sha256 != decision.artifact_sha256
    ):
        raise AgentRuntimeError("Candidate adoption must reference an eligible production result")
    if decision.selected_role == "codex_image":
        valid_identity = any(
            item.receipt.candidate_id == decision.selected_candidate_id
            and item.receipt.artifact.sha256 == decision.artifact_sha256
            for item in state.codex_image_candidates
        )
    else:
        valid_identity = any(
            item.receipt is not None
            and item.receipt.artifacts
            and item.receipt.artifacts[0].sha256 == decision.artifact_sha256
            and decision.selected_candidate_id
            == f"local-comfy:{decision.artifact_sha256[:20]}"
            for item in state.provider_executions
        )
    if not valid_identity:
        raise AgentRuntimeError("Candidate adoption identity does not match its receipt")


def _verify_revision_request_identity(
    state: AgentRunState,
    request: BoundedRevisionRequest,
) -> None:
    if state.scene is None or state.adoption_decision is None:
        raise AgentRuntimeError("Bounded revision requires scene evidence and adoption")
    adoption = state.adoption_decision
    if (
        request.adoption_decision_id != adoption.decision_id
        or request.adoption_sha256 != adoption.fingerprint()
        or request.parent_candidate_id != adoption.selected_candidate_id
        or request.parent_artifact_sha256 != adoption.artifact_sha256
        or request.scene_package_sha256 != state.scene.archive_sha256
    ):
        raise AgentRuntimeError("Bounded revision request does not match adopted evidence")
    expected_protected = {
        region.region_id
        for region in state.scene.package.regions
        if region.mode == "protected"
    }
    expected_editable = {
        region.region_id
        for region in state.scene.package.regions
        if region.mode == "editable"
    }
    if set(request.protected_regions) != expected_protected or (
        request.editable_region not in expected_editable
    ):
        raise AgentRuntimeError("Bounded revision regions do not match the Scene Package")


def _verify_revision_result_identity(
    request: BoundedRevisionRequest,
    result: BoundedRevisionResult,
) -> None:
    if (
        result.revision_id != request.revision_id
        or result.request_sha256 != request.fingerprint()
        or result.receipt.request_binding_sha256 != request.fingerprint()
        or result.leakage.parent_sha256 != request.parent_artifact_sha256
        or result.leakage.mask_sha256 != request.mask.artifact_sha256
        or result.leakage.outside_changed_pixels != 0
        or not result.leakage.hard_pass
    ):
        raise AgentRuntimeError("Bounded revision result failed identity or leakage checks")


def _verify_event_chain(events: list[AgentEvent]) -> None:
    previous_hash: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        if event.sequence != expected_sequence:
            raise AgentRuntimeError("Agent event sequence is not contiguous")
        if event.previous_hash != previous_hash:
            raise AgentRuntimeError("Agent event hash chain is broken")
        data_json = _canonical_json(event.data)
        expected_hash = _event_hash(
            run_id=event.run_id,
            sequence=event.sequence,
            event_id=event.event_id,
            event_type=event.event_type,
            occurred_at=event.occurred_at.isoformat(),
            idempotency_key=event.idempotency_key,
            data_json=data_json,
            previous_hash=event.previous_hash,
        )
        if event.event_hash != expected_hash:
            raise AgentRuntimeError("Agent event hash does not match its stored content")
        previous_hash = event.event_hash


def _event_from_row(row: sqlite3.Row | tuple[Any, ...]) -> AgentEvent:
    return AgentEvent(
        run_id=row[0],
        sequence=row[1],
        event_id=row[2],
        event_type=row[3],
        occurred_at=row[4],
        idempotency_key=row[5],
        data=json.loads(row[6]),
        previous_hash=row[7],
        event_hash=row[8],
    )


def _events_from_rows(rows: list[sqlite3.Row] | list[tuple[Any, ...]]) -> list[AgentEvent]:
    events: list[AgentEvent] = []
    for row in rows:
        try:
            events.append(_event_from_row(row))
        except (json.JSONDecodeError, ValueError) as exc:
            raise AgentRuntimeError("Agent event payload is corrupt") from exc
    return events


def _event_hash(
    *,
    run_id: str,
    sequence: int,
    event_id: str,
    event_type: str,
    occurred_at: str,
    idempotency_key: str,
    data_json: str,
    previous_hash: str | None,
) -> str:
    payload = {
        "run_id": run_id,
        "sequence": sequence,
        "event_id": event_id,
        "event_type": event_type,
        "occurred_at": occurred_at,
        "idempotency_key": idempotency_key,
        "data": json.loads(data_json),
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _validate_run_id(run_id: str) -> None:
    try:
        AgentRunState(
            run_id=run_id,
            stage="awaiting_scene",
            created_at=datetime.now(UTC),
            last_sequence=1,
        )
    except ValueError as exc:
        raise AgentRuntimeError("Agent run ID is invalid") from exc


def _find_execution(
    state: AgentRunState,
    execution_id: str,
) -> ProviderExecutionLedgerEntry:
    matches = [
        item for item in state.provider_executions if item.execution_id == execution_id
    ]
    if len(matches) != 1:
        raise AgentRuntimeError(f"Unknown provider execution: {execution_id}")
    return matches[0]
