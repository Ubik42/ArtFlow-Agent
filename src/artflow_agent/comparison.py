from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .agent_runtime import AgentEventStore, AgentRunState
from .comfy_execution import CompiledComfyRequest
from .contracts import ProviderExecutionReceipt, RouteDecision
from .hosted_execution import (
    CompiledHostedRequest,
    HostedAuthorityGate,
    HostedAuthorityPacket,
)
from .live_run import LiveRunAuthorizationDossier
from .provider_execution import ProviderExecutionCoordinator, ReconciliableProvider


class ComparisonBoundaryError(RuntimeError):
    """Raised before a comparison can cross either provider boundary."""


class ComparisonChildPlan(BaseModel):
    role: Literal["local", "hosted"]
    action_id: str
    run_id: str
    execution_id: str
    idempotency_key: str
    provider_id: str
    model_id: str
    route_decision_id: str
    route_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    attestation_environment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    authority_kind: Literal["bounded_local_compute", "hosted_privacy_cost"]


class ComparisonOperatorPreview(BaseModel):
    local_uploads: list[Literal["beauty"]]
    hosted_uploads: list[Literal["beauty"]]
    hosted_endpoint: Literal["/v1/images/edits"]
    hosted_model: Literal["gpt-image-2-2026-04-21"]
    output_count_per_provider: Literal[1]
    output_size: str
    estimated_hosted_cost_usd: float = Field(ge=0)
    maximum_hosted_cost_usd: float = Field(gt=0)
    hosted_privacy_class: Literal["provider_retained"]
    cost_cap_provider_enforced: Literal[False]
    unresolved_real_host_facts: list[str] = Field(min_length=1)


class ProviderComparisonPlan(BaseModel):
    schema_id: Literal["provider-comparison-plan/1"] = "provider-comparison-plan/1"
    comparison_id: str
    dossier_id: str
    dossier_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scene_package_id: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    art_intent_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    children: list[ComparisonChildPlan] = Field(min_length=2, max_length=2)
    operator_preview: ComparisonOperatorPreview

    @model_validator(mode="after")
    def require_independent_children(self) -> ProviderComparisonPlan:
        by_role = {child.role: child for child in self.children}
        if set(by_role) != {"local", "hosted"}:
            raise ValueError("Comparison requires exactly one local and one hosted child")
        local, hosted = by_role["local"], by_role["hosted"]
        if local.authority_kind != "bounded_local_compute":
            raise ValueError("Local child must use bounded project-local compute")
        if hosted.authority_kind != "hosted_privacy_cost":
            raise ValueError("Hosted child requires privacy and cost authority")
        for field in (
            "action_id",
            "run_id",
            "execution_id",
            "idempotency_key",
            "route_decision_id",
            "route_fingerprint",
            "attestation_environment_sha256",
        ):
            if getattr(local, field) == getattr(hosted, field):
                raise ValueError(f"Comparison children must not share {field}")
        return self

    def approval_binding(self) -> str:
        return _sha256(self.model_dump(mode="json"))


class ComparisonAuthorizationDecision(BaseModel):
    schema_id: Literal["comparison-authorization-decision/1"] = (
        "comparison-authorization-decision/1"
    )
    dossier_id: str
    dossier_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    comparison_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    resolution: Literal["approved"]
    approved_by: str = Field(min_length=1)
    approved_at: AwareDatetime
    authorized_action_ids: list[str] = Field(min_length=1, max_length=1)


class ComparisonChildResult(BaseModel):
    role: Literal["local", "hosted"]
    run_id: str
    execution_id: str
    provider_id: str
    model_id: str
    status: Literal[
        "not_started",
        "reserved",
        "submitted",
        "completion_unknown",
        "succeeded",
        "failed",
        "cancelled",
    ]
    receipt: ProviderExecutionReceipt | None = None

    @model_validator(mode="after")
    def require_receipt_only_for_terminal_result(self) -> ComparisonChildResult:
        terminal = self.status in {"succeeded", "failed", "cancelled"}
        if terminal != (self.receipt is not None):
            raise ValueError("Comparison terminal child status and receipt must agree")
        return self


class ProviderComparisonManifest(BaseModel):
    schema_id: Literal["provider-comparison-manifest/1"] = (
        "provider-comparison-manifest/1"
    )
    comparison_id: str
    comparison_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["not_started", "partial", "succeeded", "failed", "needs_human_recovery"]
    children: list[ComparisonChildResult] = Field(min_length=2, max_length=2)
    human_selected_candidate_id: None = None

    @model_validator(mode="after")
    def require_truthful_aggregate_status(self) -> ProviderComparisonManifest:
        statuses = {child.status for child in self.children}
        expected = "partial"
        if statuses == {"succeeded"}:
            expected = "succeeded"
        elif "completion_unknown" in statuses:
            expected = "needs_human_recovery"
        elif statuses & {"failed", "cancelled"}:
            expected = "failed"
        elif statuses == {"not_started"}:
            expected = "not_started"
        if self.status != expected:
            raise ValueError("Comparison aggregate status does not match child evidence")
        return self


class ComparisonPlanCompiler:
    @staticmethod
    def compile(
        dossier: LiveRunAuthorizationDossier,
        *,
        comparison_id: str,
        local_run_id: str,
        hosted_run_id: str,
        local_decision: RouteDecision,
        hosted_decision: RouteDecision,
        local_attestation_sha256: str,
        hosted_attestation_sha256: str,
        estimated_hosted_cost_usd: float,
    ) -> ProviderComparisonPlan:
        decisions = (local_decision, hosted_decision)
        for decision in decisions:
            if (
                decision.scene_package_id != dossier.scene_package_id
                or decision.scene_package_sha256 != dossier.scene_package_sha256
            ):
                raise ComparisonBoundaryError("Comparison route uses a stale Scene Package")
        if (
            local_decision.execution_intent.intent_sha256
            != hosted_decision.execution_intent.intent_sha256
        ):
            raise ComparisonBoundaryError("Comparison routes do not share one art intent")
        if (
            local_decision.selected.provider_id != dossier.local_provider_id
            or local_decision.selected.execution_kind != "local"
        ):
            raise ComparisonBoundaryError("Local comparison route identity drifted")
        if (
            hosted_decision.selected.provider_id != dossier.hosted_provider_id
            or hosted_decision.selected.model_id != dossier.hosted_model_snapshot
            or hosted_decision.selected.execution_kind != "hosted"
            or hosted_decision.selected.privacy_class != dossier.hosted_privacy_class
        ):
            raise ComparisonBoundaryError("Hosted comparison route identity drifted")
        if estimated_hosted_cost_usd > dossier.maximum_approved_cost_usd:
            raise ComparisonBoundaryError("Estimated hosted cost exceeds dossier ceiling")
        if local_attestation_sha256 != dossier.local_attestation_sha256:
            raise ComparisonBoundaryError("Local attestation does not match the dossier")
        local_action = _action_id(dossier, "comfy-local")
        hosted_action = _action_id(dossier, "openai-images")
        return ProviderComparisonPlan(
            comparison_id=comparison_id,
            dossier_id=dossier.dossier_id,
            dossier_sha256=_sha256(dossier.model_dump(mode="json")),
            scene_package_id=dossier.scene_package_id,
            scene_package_sha256=dossier.scene_package_sha256,
            art_intent_sha256=local_decision.execution_intent.intent_sha256,
            children=[
                ComparisonChildPlan(
                    role="local",
                    action_id=local_action,
                    run_id=local_run_id,
                    execution_id=f"{comparison_id}-local",
                    idempotency_key=f"comparison:{comparison_id}:local",
                    provider_id=local_decision.selected.provider_id,
                    model_id=local_decision.selected.model_id,
                    route_decision_id=local_decision.decision_id,
                    route_fingerprint=local_decision.approval_fingerprint(),
                    attestation_environment_sha256=local_attestation_sha256,
                    authority_kind="bounded_local_compute",
                ),
                ComparisonChildPlan(
                    role="hosted",
                    action_id=hosted_action,
                    run_id=hosted_run_id,
                    execution_id=f"{comparison_id}-hosted",
                    idempotency_key=f"comparison:{comparison_id}:hosted",
                    provider_id=hosted_decision.selected.provider_id,
                    model_id=hosted_decision.selected.model_id,
                    route_decision_id=hosted_decision.decision_id,
                    route_fingerprint=hosted_decision.approval_fingerprint(),
                    attestation_environment_sha256=hosted_attestation_sha256,
                    authority_kind="hosted_privacy_cost",
                ),
            ],
            operator_preview=ComparisonOperatorPreview(
                local_uploads=["beauty"],
                hosted_uploads=["beauty"],
                hosted_endpoint=dossier.hosted_endpoint,
                hosted_model=dossier.hosted_model_snapshot,
                output_count_per_provider=dossier.output_count,
                output_size=dossier.output_size,
                estimated_hosted_cost_usd=estimated_hosted_cost_usd,
                maximum_hosted_cost_usd=dossier.maximum_approved_cost_usd,
                hosted_privacy_class=dossier.hosted_privacy_class,
                cost_cap_provider_enforced=dossier.cost_is_provider_enforced,
                unresolved_real_host_facts=list(dossier.unresolved_requirements),
            ),
        )


class ProviderComparisonLauncher:
    def __init__(self, store: AgentEventStore) -> None:
        self.store = store

    def launch_or_resume(
        self,
        plan: ProviderComparisonPlan,
        dossier: LiveRunAuthorizationDossier,
        authorization: ComparisonAuthorizationDecision | None,
        *,
        local_decision: RouteDecision,
        hosted_decision: RouteDecision,
        local_compiled: CompiledComfyRequest,
        hosted_compiled: CompiledHostedRequest,
        hosted_authority: HostedAuthorityPacket | None,
        hosted_gate: HostedAuthorityGate,
        local_provider: ReconciliableProvider,
        hosted_provider: ReconciliableProvider,
    ) -> ProviderComparisonManifest:
        children = {child.role: child for child in plan.children}
        if not _decision_matches(children["local"], local_decision) or not _decision_matches(
            children["hosted"], hosted_decision
        ):
            raise ComparisonBoundaryError("Comparison route decision identity drifted")
        needs_local = self._needs_submission(children["local"])
        needs_hosted = self._needs_submission(children["hosted"])
        if needs_local or needs_hosted:
            self._preflight(
                plan,
                dossier,
                authorization,
                local_compiled=local_compiled,
                hosted_compiled=hosted_compiled,
                hosted_authority=hosted_authority,
                hosted_gate=hosted_gate,
                needs_local=needs_local,
                needs_hosted=needs_hosted,
            )
        decisions = {"local": local_decision, "hosted": hosted_decision}
        providers = {"local": local_provider, "hosted": hosted_provider}
        for role in ("local", "hosted"):
            child = children[role]
            ProviderExecutionCoordinator(self.store, providers[role]).run_or_reconcile(
                child.run_id,
                child.execution_id,
                child.idempotency_key,
                decisions[role],
            )
        return self.collect(plan)

    def collect(self, plan: ProviderComparisonPlan) -> ProviderComparisonManifest:
        results: list[ComparisonChildResult] = []
        for child in plan.children:
            state = self.store.load(child.run_id)
            _verify_child_state(plan, child, state)
            execution = next(
                (item for item in state.provider_executions if item.execution_id == child.execution_id),
                None,
            )
            results.append(
                ComparisonChildResult(
                    role=child.role,
                    run_id=child.run_id,
                    execution_id=child.execution_id,
                    provider_id=child.provider_id,
                    model_id=child.model_id,
                    status=execution.status if execution else "not_started",
                    receipt=execution.receipt if execution else None,
                )
            )
        statuses = {item.status for item in results}
        if statuses == {"succeeded"}:
            status = "succeeded"
        elif "completion_unknown" in statuses:
            status = "needs_human_recovery"
        elif statuses & {"failed", "cancelled"}:
            status = "failed"
        elif statuses == {"not_started"}:
            status = "not_started"
        else:
            status = "partial"
        return ProviderComparisonManifest(
            comparison_id=plan.comparison_id,
            comparison_binding_sha256=plan.approval_binding(),
            scene_package_sha256=plan.scene_package_sha256,
            status=status,
            children=results,
        )

    def _needs_submission(self, child: ComparisonChildPlan) -> bool:
        state = self.store.load(child.run_id)
        execution = next(
            (item for item in state.provider_executions if item.execution_id == child.execution_id),
            None,
        )
        return execution is None or execution.status == "reserved"

    def _preflight(
        self,
        plan: ProviderComparisonPlan,
        dossier: LiveRunAuthorizationDossier,
        authorization: ComparisonAuthorizationDecision | None,
        *,
        local_compiled: CompiledComfyRequest,
        hosted_compiled: CompiledHostedRequest,
        hosted_authority: HostedAuthorityPacket | None,
        hosted_gate: HostedAuthorityGate,
        needs_local: bool,
        needs_hosted: bool,
    ) -> None:
        for child in plan.children:
            _verify_child_state(plan, child, self.store.load(child.run_id))
        dossier_sha = _sha256(dossier.model_dump(mode="json"))
        if needs_hosted and authorization is None:
            raise ComparisonBoundaryError("Live-run dossier is still awaiting user authorization")
        if needs_hosted and authorization is not None and (
            authorization.dossier_id != dossier.dossier_id
            or authorization.dossier_sha256 != dossier_sha
            or plan.dossier_sha256 != dossier_sha
            or authorization.comparison_binding_sha256 != plan.approval_binding()
        ):
            raise ComparisonBoundaryError("Comparison authorization identity drifted")
        local = next(child for child in plan.children if child.role == "local")
        hosted = next(child for child in plan.children if child.role == "hosted")
        expected_actions = {hosted.action_id}
        if (
            needs_hosted
            and authorization is not None
            and set(authorization.authorized_action_ids) != expected_actions
        ):
            raise ComparisonBoundaryError("Hosted authorization has partial or expanded scope")
        if not _compiled_matches(local, local_compiled) or not _compiled_matches(
            hosted, hosted_compiled
        ):
            raise ComparisonBoundaryError("Compiled comparison child identity drifted")
        if needs_hosted:
            if hosted_authority is None:
                raise ComparisonBoundaryError("Hosted privacy and cost authority is missing")
            hosted_gate.verify(hosted_authority, hosted_compiled)


def _compiled_matches(
    child: ComparisonChildPlan,
    request: CompiledComfyRequest | CompiledHostedRequest,
) -> bool:
    identity_matches = (
        child.run_id == request.run_id
        and child.execution_id == request.execution_id
        and child.route_decision_id == request.route_decision_id
        and child.route_fingerprint == request.route_fingerprint
        and child.provider_id == request.provider_id
        and child.model_id == request.model_id
        and child.attestation_environment_sha256
        == request.attestation_environment_sha256
    )
    if isinstance(request, CompiledHostedRequest):
        identity_matches = (
            identity_matches and child.idempotency_key == request.idempotency_key
        )
    return identity_matches


def _decision_matches(child: ComparisonChildPlan, decision: RouteDecision) -> bool:
    return (
        child.route_decision_id == decision.decision_id
        and child.route_fingerprint == decision.approval_fingerprint()
        and child.provider_id == decision.selected.provider_id
        and child.model_id == decision.selected.model_id
    )


def _verify_child_state(
    plan: ProviderComparisonPlan,
    child: ComparisonChildPlan,
    state: AgentRunState,
) -> None:
    if state.scene is None or state.route_decision is None:
        raise ComparisonBoundaryError("Comparison child run is incomplete")
    if (
        state.scene.archive_sha256 != plan.scene_package_sha256
        or state.scene.package.package_id != plan.scene_package_id
        or state.route_decision.decision_id != child.route_decision_id
        or state.route_decision.approval_fingerprint() != child.route_fingerprint
        or state.route_decision.selected.provider_id != child.provider_id
        or state.route_decision.selected.model_id != child.model_id
    ):
        raise ComparisonBoundaryError("Comparison child durable identity drifted")
    attestation = next(
        (
            item
            for item in state.capability_attestations
            if item.environment_sha256 == child.attestation_environment_sha256
        ),
        None,
    )
    if (
        attestation is None
        or attestation.status != "supported"
        or attestation.provider_id != child.provider_id
        or attestation.model_id != child.model_id
    ):
        raise ComparisonBoundaryError("Comparison child attestation is stale or unsupported")


def _action_id(dossier: LiveRunAuthorizationDossier, target: str) -> str:
    matches = [action.action_id for action in dossier.actions if action.target == target]
    if len(matches) != 1:
        raise ComparisonBoundaryError(f"Dossier must declare exactly one {target} action")
    return matches[0]


def _sha256(value: object) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
