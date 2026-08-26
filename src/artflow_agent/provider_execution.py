from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Literal, Protocol

from opentelemetry.trace import Span
from pydantic import BaseModel, Field, model_validator

from .agent_runtime import AgentEventStore, AgentRunState, AgentRuntimeError
from .contracts import ProviderExecutionReceipt, ReceiptArtifact, RouteDecision
from .observability import TraceRecorder, hashed_trace_value, set_safe_attributes

FailureInjectionPoint = Literal[
    "before_reservation",
    "after_reservation",
    "after_submit",
    "after_artifact_verification",
]


class ProviderExecutionError(RuntimeError):
    """Raised when an external execution cannot be safely submitted or verified."""


class ProviderCompletionUnknown(ProviderExecutionError):
    """The side effect may have happened and must never be retried automatically."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class SimulatedCoordinatorCrash(RuntimeError):
    """Failure injection after the provider observed submission but before local acknowledgement."""


class ProviderExecutionRequest(BaseModel):
    execution_id: str
    idempotency_key: str
    route_decision: RouteDecision
    attestation_environment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class ProviderSubmission(BaseModel):
    provider_request_id: str = Field(min_length=1)


class ProviderObservation(BaseModel):
    provider_request_id: str
    status: Literal["running", "terminal"]
    receipt: ProviderExecutionReceipt | None = None

    @model_validator(mode="after")
    def require_terminal_receipt(self) -> ProviderObservation:
        if self.status == "terminal" and self.receipt is None:
            raise ValueError("terminal provider observation requires a receipt")
        if self.status == "running" and self.receipt is not None:
            raise ValueError("running provider observation cannot contain a receipt")
        return self


class ReconciliableProvider(Protocol):
    def submit(self, request: ProviderExecutionRequest) -> ProviderSubmission: ...

    def lookup(self, idempotency_key: str) -> ProviderObservation | None: ...

    def fetch_artifact(self, provider_request_id: str, path: str) -> bytes: ...


class ProviderExecutionCoordinator:
    """Durable-before-side-effect coordinator with unknown-completion reconciliation."""

    def __init__(
        self,
        store: AgentEventStore,
        provider: ReconciliableProvider,
        trace_recorder: TraceRecorder | None = None,
    ) -> None:
        self.store = store
        self.provider = provider
        self.trace_recorder = trace_recorder

    def run_or_reconcile(
        self,
        run_id: str,
        execution_id: str,
        idempotency_key: str,
        decision: RouteDecision,
        *,
        crash_after_submit: bool = False,
        inject_failure_at: FailureInjectionPoint | None = None,
    ) -> AgentRunState:
        injection = "after_submit" if crash_after_submit else inject_failure_at
        attributes = {
            "artflow.run_id": run_id,
            "artflow.execution_id": execution_id,
            "artflow.idempotency_key_sha256": hashed_trace_value(idempotency_key),
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.provider.name": decision.selected.provider_id,
            "gen_ai.request.model": decision.selected.model_id,
        }
        with self._phase_span("invoke_agent", attributes) as root_span:
            try:
                state = self._run_or_reconcile(
                    run_id,
                    execution_id,
                    idempotency_key,
                    decision,
                    injection,
                )
            except Exception:
                if root_span is not None:
                    trace_attributes: dict[str, str | int] = {
                        "artflow.outcome": "interrupted"
                    }
                    try:
                        trace_attributes["artflow.event_sequence"] = self.store.load(
                            run_id
                        ).last_sequence
                    except AgentRuntimeError:
                        pass
                    set_safe_attributes(root_span, trace_attributes)
                raise
            if root_span is not None:
                set_safe_attributes(
                    root_span,
                    {
                        "artflow.outcome": state.stage,
                        "artflow.event_sequence": state.last_sequence,
                        "artflow.side_effect_count": getattr(
                            self.provider, "submit_calls", 0
                        ),
                    },
                )
            return state

    def _run_or_reconcile(
        self,
        run_id: str,
        execution_id: str,
        idempotency_key: str,
        decision: RouteDecision,
        injection: FailureInjectionPoint | None,
    ) -> AgentRunState:
        if injection == "before_reservation":
            raise SimulatedCoordinatorCrash("Injected crash before durable reservation")
        with self._phase_span(
            "artflow.reserve_execution",
            {"artflow.phase": "durable_reservation"},
        ):
            state = self.store.reserve_provider_execution(
                run_id,
                execution_id,
                idempotency_key,
                decision,
            )
        if injection == "after_reservation":
            raise SimulatedCoordinatorCrash("Injected crash after durable reservation")
        execution = _execution(state, execution_id)
        if execution.status in {"succeeded", "failed", "cancelled"}:
            return state

        with self._phase_span(
            "artflow.lookup_execution",
            {
                "artflow.phase": "provider_reconciliation",
                "artflow.retry_suppressed": execution.status == "completion_unknown",
            },
        ) as lookup_span:
            observation = self.provider.lookup(idempotency_key)
            if lookup_span is not None:
                set_safe_attributes(
                    lookup_span,
                    {
                        "artflow.outcome": (
                            observation.status if observation is not None else "not_found"
                        )
                    },
                )
        if execution.status == "reserved":
            if observation is None:
                request = ProviderExecutionRequest(
                    execution_id=execution_id,
                    idempotency_key=idempotency_key,
                    route_decision=decision,
                    attestation_environment_sha256=(
                        execution.attestation_environment_sha256
                    ),
                )
                with self._phase_span(
                    "execute_tool",
                    {
                        "artflow.phase": "provider_submission",
                        "artflow.capability_id": "provider.execute",
                        "gen_ai.operation.name": "execute_tool",
                        "gen_ai.provider.name": decision.selected.provider_id,
                        "gen_ai.request.model": decision.selected.model_id,
                    },
                ) as submit_span:
                    try:
                        submission = self.provider.submit(request)
                    except ProviderCompletionUnknown as exc:
                        if submit_span is not None:
                            set_safe_attributes(
                                submit_span,
                                {
                                    "artflow.outcome": "completion_unknown",
                                    "artflow.retry_suppressed": True,
                                },
                            )
                        return self.store.mark_provider_completion_unknown(
                            run_id,
                            execution_id,
                            exc.reason,
                        )
                    if submit_span is not None:
                        set_safe_attributes(
                            submit_span,
                            {
                                "artflow.outcome": "accepted",
                                "artflow.provider_request_id_sha256": hashed_trace_value(
                                    submission.provider_request_id
                                ),
                                "artflow.side_effect_count": getattr(
                                    self.provider, "submit_calls", 0
                                ),
                            },
                        )
                if injection == "after_submit":
                    raise SimulatedCoordinatorCrash(
                        "Injected crash after provider submission and before local acknowledgement"
                    )
                self.store.record_provider_submission(
                    run_id,
                    execution_id,
                    submission.provider_request_id,
                )
                observation = self.provider.lookup(idempotency_key)
            else:
                if self.trace_recorder is not None:
                    with self._phase_span(
                        "artflow.recover_submission_ack",
                        {
                            "artflow.phase": "recovery",
                            "artflow.recovery_action": "reuse_provider_lookup",
                            "artflow.retry_suppressed": True,
                            "artflow.provider_request_id_sha256": hashed_trace_value(
                                observation.provider_request_id
                            ),
                        },
                    ):
                        pass
                self.store.record_provider_submission(
                    run_id,
                    execution_id,
                    observation.provider_request_id,
                )
        if observation is None:
            return self.store.mark_provider_completion_unknown(
                run_id,
                execution_id,
                "provider_request_not_observable",
            )
        if observation.status == "running":
            return self.store.mark_provider_completion_unknown(
                run_id,
                execution_id,
                "observation_deadline_exhausted",
            )
        receipt = observation.receipt
        if receipt is None:
            raise ProviderExecutionError("Terminal observation omitted its receipt")
        with self._phase_span(
            "artflow.verify_provider_artifacts",
            {
                "artflow.phase": "receipt_verification",
                "artflow.provider_request_id_sha256": hashed_trace_value(
                    receipt.provider_request_id or ""
                ),
            },
        ):
            self._verify_artifacts(receipt)
        if injection == "after_artifact_verification":
            raise SimulatedCoordinatorCrash(
                "Injected crash after artifact verification and before receipt commit"
            )
        return self.store.record_provider_receipt(run_id, receipt)

    @contextmanager
    def _phase_span(
        self,
        name: str,
        attributes: dict[str, str | int | float | bool],
    ) -> Iterator[Span | None]:
        if self.trace_recorder is None:
            yield None
            return
        with self.trace_recorder.span(name, attributes) as span:
            yield span

    def _verify_artifacts(self, receipt: ProviderExecutionReceipt) -> None:
        paths: set[str] = set()
        for artifact in receipt.artifacts:
            if artifact.path in paths:
                raise ProviderExecutionError("Provider receipt contains duplicate artifact paths")
            paths.add(artifact.path)
            content = self.provider.fetch_artifact(
                receipt.provider_request_id or "",
                artifact.path,
            )
            digest = hashlib.sha256(content).hexdigest()
            if digest != artifact.sha256:
                raise ProviderExecutionError(
                    f"Provider artifact hash mismatch: {artifact.path}"
                )


class OfflineProviderSimulator:
    """Stateful fake external system used to prove reconciliation without a real provider."""

    def __init__(self) -> None:
        self.submit_calls = 0
        self._jobs: dict[str, dict[str, object]] = {}

    def submit(self, request: ProviderExecutionRequest) -> ProviderSubmission:
        existing = self._jobs.get(request.idempotency_key)
        if existing is not None:
            return ProviderSubmission(provider_request_id=str(existing["provider_request_id"]))
        self.submit_calls += 1
        provider_request_id = f"sim-{uuid.uuid4().hex}"
        self._jobs[request.idempotency_key] = {
            "request": request,
            "provider_request_id": provider_request_id,
            "receipt": None,
            "artifacts": {},
        }
        return ProviderSubmission(provider_request_id=provider_request_id)

    def lookup(self, idempotency_key: str) -> ProviderObservation | None:
        job = self._jobs.get(idempotency_key)
        if job is None:
            return None
        receipt = job["receipt"]
        return ProviderObservation(
            provider_request_id=str(job["provider_request_id"]),
            status="terminal" if receipt is not None else "running",
            receipt=receipt,
        )

    def fetch_artifact(self, provider_request_id: str, path: str) -> bytes:
        for job in self._jobs.values():
            if job["provider_request_id"] == provider_request_id:
                artifacts = job["artifacts"]
                if isinstance(artifacts, dict) and path in artifacts:
                    return bytes(artifacts[path])
        raise ProviderExecutionError(f"Simulated provider artifact is missing: {path}")

    def succeed(self, idempotency_key: str, artifacts: dict[str, bytes]) -> None:
        job = self._job(idempotency_key)
        request = job["request"]
        if not isinstance(request, ProviderExecutionRequest):
            raise ProviderExecutionError("Simulated request state is corrupt")
        now = datetime.now(UTC)
        receipt_artifacts = [
            ReceiptArtifact(
                path=path,
                sha256=hashlib.sha256(content).hexdigest(),
                media_type="image/png",
            )
            for path, content in sorted(artifacts.items())
        ]
        job["artifacts"] = dict(artifacts)
        job["receipt"] = ProviderExecutionReceipt(
            execution_id=request.execution_id,
            route_decision_id=request.route_decision.decision_id,
            route_fingerprint=request.route_decision.approval_fingerprint(),
            provider_id=request.route_decision.selected.provider_id,
            model_id=request.route_decision.selected.model_id,
            status="succeeded",
            started_at=now,
            completed_at=now,
            provider_request_id=str(job["provider_request_id"]),
            artifacts=receipt_artifacts,
        )

    def tamper_artifact(self, idempotency_key: str, path: str, content: bytes) -> None:
        job = self._job(idempotency_key)
        artifacts = job["artifacts"]
        if not isinstance(artifacts, dict):
            raise ProviderExecutionError("Simulated artifact state is corrupt")
        artifacts[path] = content

    def _job(self, idempotency_key: str) -> dict[str, object]:
        try:
            return self._jobs[idempotency_key]
        except KeyError as exc:
            raise ProviderExecutionError("Simulated provider has no matching request") from exc


def _execution(state: AgentRunState, execution_id: str):
    matches = [
        item for item in state.provider_executions if item.execution_id == execution_id
    ]
    if len(matches) != 1:
        raise AgentRuntimeError(f"Unknown provider execution: {execution_id}")
    return matches[0]
