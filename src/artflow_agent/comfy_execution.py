from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from .agent_runtime import AgentEventStore
from .contracts import ProviderExecutionReceipt, ReceiptArtifact
from .domain import OutputArtifact, QueuedJob, UploadedInput
from .provider_execution import (
    ProviderExecutionRequest,
    ProviderObservation,
    ProviderSubmission,
)
from .recipes import RecipeCatalog, RecipeError


class ComfyExecutionBoundaryError(RuntimeError):
    """Raised before an unapproved or stale ComfyUI side effect can occur."""


class CompiledComfyRequest(BaseModel):
    schema_id: str = "compiled-comfy-request/1"
    run_id: str
    execution_id: str
    route_decision_id: str
    route_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_id: str
    model_id: str
    scene_package_id: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    attestation_environment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    recipe_id: str
    recipe_version: str
    workflow_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_artifact_path: str
    source_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    workflow: dict[str, Any]

    def execution_binding(self) -> str:
        facts = {
            "execution_id": self.execution_id,
            "route_fingerprint": self.route_fingerprint,
            "attestation_environment_sha256": self.attestation_environment_sha256,
            "workflow_sha256": self.workflow_sha256,
        }
        return _sha256(facts)


class ComfyWorkflowCompiler:
    """Compiles only bundled reviewed recipes from persisted authoritative run state."""

    def __init__(self, store: AgentEventStore, catalog: RecipeCatalog | None = None) -> None:
        self.store = store
        self.catalog = catalog or RecipeCatalog.bundled()

    def compile(
        self,
        run_id: str,
        execution_id: str,
        recipe_id: str,
        values: dict[str, Any],
    ) -> CompiledComfyRequest:
        state = self.store.load(run_id)
        if state.scene is None or state.route_decision is None:
            raise ComfyExecutionBoundaryError("Execution context is incomplete")
        try:
            execution = next(
                item for item in state.provider_executions if item.execution_id == execution_id
            )
        except StopIteration as exc:
            raise ComfyExecutionBoundaryError("Execution must be durably reserved first") from exc
        decision = state.route_decision
        if execution.status != "reserved":
            raise ComfyExecutionBoundaryError("Only a reserved execution can be compiled")
        if execution.route_fingerprint != decision.approval_fingerprint():
            raise ComfyExecutionBoundaryError("Execution route approval is stale")
        attestation = next(
            (
                item
                for item in state.capability_attestations
                if item.environment_sha256 == execution.attestation_environment_sha256
            ),
            None,
        )
        if attestation is None or attestation.status != "supported":
            raise ComfyExecutionBoundaryError("Execution attestation is stale or unsupported")
        recipe = self.catalog.get(recipe_id)
        if recipe.definition.recipe_id != attestation.recipe_id:
            raise ComfyExecutionBoundaryError("Reviewed recipe does not match attestation")
        if recipe.definition.task_type != decision.task:
            raise ComfyExecutionBoundaryError("Reviewed recipe does not match route task")
        if values.get("width") != decision.execution_intent.width or values.get(
            "height"
        ) != decision.execution_intent.height:
            raise ComfyExecutionBoundaryError("Workflow dimensions do not match approved intent")
        source = next(
            (item for item in state.scene.artifacts if item.path.endswith("beauty.png")),
            None,
        )
        if source is None:
            raise ComfyExecutionBoundaryError("Scene Package has no verified beauty input")
        expected_remote = f"ArtFlow/{execution_id}/{Path(source.path).name}"
        expected_prefix = f"ArtFlow/{execution_id}/composition"
        if values.get("source_image") != expected_remote:
            raise ComfyExecutionBoundaryError("Source image path is not compiler-owned")
        if values.get("filename_prefix") != expected_prefix:
            raise ComfyExecutionBoundaryError("Output prefix is not compiler-owned")
        for name in ("positive_prompt", "negative_prompt"):
            value = values.get(name)
            if not isinstance(value, str) or not value.strip() or len(value) > 4000 or "\x00" in value:
                raise ComfyExecutionBoundaryError(f"Invalid bounded prompt slot: {name}")
        try:
            workflow = recipe.instantiate(values)
        except RecipeError as exc:
            raise ComfyExecutionBoundaryError(str(exc)) from exc
        workflow_sha256 = _sha256(workflow)
        return CompiledComfyRequest(
            run_id=run_id,
            execution_id=execution_id,
            route_decision_id=decision.decision_id,
            route_fingerprint=decision.approval_fingerprint(),
            provider_id=decision.selected.provider_id,
            model_id=decision.selected.model_id,
            scene_package_id=state.scene.package.package_id,
            scene_package_sha256=state.scene.archive_sha256,
            attestation_environment_sha256=attestation.environment_sha256,
            recipe_id=recipe.definition.recipe_id,
            recipe_version=recipe.definition.version,
            workflow_sha256=workflow_sha256,
            source_artifact_path=source.path,
            source_artifact_sha256=source.sha256,
            workflow=workflow,
        )


class ComfySideEffectTransport(Protocol):
    def upload_image(self, path: Path, *, subfolder: str) -> UploadedInput: ...
    def queue(self, workflow: Mapping[str, Any], client_id: str | None = None) -> QueuedJob: ...
    def history(self, prompt_id: str) -> dict[str, Any] | None: ...
    def collect_outputs(self, history_entry: Mapping[str, Any]) -> list[OutputArtifact]: ...
    def fetch_output_bytes(self, artifact: OutputArtifact) -> bytes: ...


class BoundedComfyAdapter:
    """Executes only content-bound requests compiled from reviewed local recipes."""

    def __init__(self, transport: ComfySideEffectTransport) -> None:
        self.transport = transport
        self._normalized_artifacts: dict[tuple[str, str], bytes] = {}

    def submit(
        self,
        request: CompiledComfyRequest,
        source_path: Path,
    ) -> QueuedJob:
        if hashlib.sha256(source_path.read_bytes()).hexdigest() != request.source_artifact_sha256:
            raise ComfyExecutionBoundaryError("Source artifact hash does not match compiled request")
        subfolder = f"ArtFlow/{request.execution_id}"
        uploaded = self.transport.upload_image(source_path, subfolder=subfolder)
        expected = f"{subfolder}/{source_path.name}"
        observed = "/".join(part for part in (uploaded.subfolder, uploaded.name) if part)
        if observed != expected:
            raise ComfyExecutionBoundaryError("ComfyUI upload identity does not match request")
        return self.transport.queue(request.workflow, client_id=request.execution_id)

    def normalize_terminal_receipt(
        self,
        request: CompiledComfyRequest,
        prompt_id: str,
    ) -> ProviderExecutionReceipt | None:
        history = self.transport.history(prompt_id)
        if history is None:
            return None
        status = history.get("status") or {}
        completed = status.get("completed") is True or bool(history.get("outputs"))
        failed = status.get("status_str") == "error"
        if not completed and not failed:
            return None
        now = datetime.now(UTC)
        if failed:
            return ProviderExecutionReceipt(
                execution_id=request.execution_id,
                route_decision_id=request.route_decision_id,
                route_fingerprint=request.route_fingerprint,
                provider_id=request.provider_id,
                model_id=request.model_id,
                status="failed",
                started_at=now,
                completed_at=now,
                provider_request_id=prompt_id,
                error_code="comfy_execution_failed",
            )
        artifacts: list[ReceiptArtifact] = []
        for output in self.transport.collect_outputs(history):
            content = self.transport.fetch_output_bytes(output)
            path = "/".join(
                part for part in (output.subfolder, output.filename) if part
            )
            artifacts.append(
                ReceiptArtifact(
                    path=path,
                    sha256=hashlib.sha256(content).hexdigest(),
                    media_type="image/png",
                )
            )
            self._normalized_artifacts[(prompt_id, path)] = content
        if not artifacts:
            raise ComfyExecutionBoundaryError("Completed ComfyUI history has no outputs")
        return ProviderExecutionReceipt(
            execution_id=request.execution_id,
            route_decision_id=request.route_decision_id,
            route_fingerprint=request.route_fingerprint,
            provider_id=request.provider_id,
            model_id=request.model_id,
            status="succeeded",
            started_at=now,
            completed_at=now,
            provider_request_id=prompt_id,
            artifacts=artifacts,
        )

    def fetch_normalized_artifact(self, prompt_id: str, path: str) -> bytes:
        try:
            return self._normalized_artifacts[(prompt_id, path)]
        except KeyError as exc:
            raise ComfyExecutionBoundaryError(
                "Comfy receipt artifact was not normalized by this adapter"
            ) from exc


class ComfyProviderAdapter:
    """Makes the reviewed Comfy boundary implement the common durable provider port."""

    def __init__(
        self,
        request: CompiledComfyRequest,
        *,
        adapter: BoundedComfyAdapter,
        source_path: Path,
        idempotency_key: str,
        known_prompt_id: str | None = None,
        observation_timeout_seconds: float = 0,
        poll_interval_seconds: float = 1,
    ) -> None:
        self.request = request
        self.adapter = adapter
        self.source_path = source_path
        self.idempotency_key = idempotency_key
        self._prompt_id = known_prompt_id
        self.observation_timeout_seconds = observation_timeout_seconds
        self.poll_interval_seconds = poll_interval_seconds

    def submit(self, execution: ProviderExecutionRequest) -> ProviderSubmission:
        self._verify_execution(execution)
        job = self.adapter.submit(self.request, self.source_path)
        self._prompt_id = job.prompt_id
        return ProviderSubmission(provider_request_id=job.prompt_id)

    def lookup(self, idempotency_key: str) -> ProviderObservation | None:
        if idempotency_key != self.idempotency_key:
            raise ComfyExecutionBoundaryError("Comfy lookup identity drifted")
        if self._prompt_id is None:
            return None
        deadline = time.monotonic() + self.observation_timeout_seconds
        while True:
            receipt = self.adapter.normalize_terminal_receipt(
                self.request, self._prompt_id
            )
            if receipt is not None:
                break
            if time.monotonic() >= deadline:
                return ProviderObservation(
                    provider_request_id=self._prompt_id,
                    status="running",
                )
            time.sleep(self.poll_interval_seconds)
        return ProviderObservation(
            provider_request_id=self._prompt_id,
            status="terminal",
            receipt=receipt,
        )

    def fetch_artifact(self, provider_request_id: str, path: str) -> bytes:
        if provider_request_id != self._prompt_id:
            raise ComfyExecutionBoundaryError("Comfy output identity drifted")
        return self.adapter.fetch_normalized_artifact(provider_request_id, path)

    def _verify_execution(self, execution: ProviderExecutionRequest) -> None:
        decision = execution.route_decision
        if (
            execution.execution_id != self.request.execution_id
            or execution.idempotency_key != self.idempotency_key
            or decision.decision_id != self.request.route_decision_id
            or decision.approval_fingerprint() != self.request.route_fingerprint
            or decision.selected.provider_id != self.request.provider_id
            or decision.selected.model_id != self.request.model_id
            or decision.selected.execution_kind != "local"
            or execution.attestation_environment_sha256
            != self.request.attestation_environment_sha256
        ):
            raise ComfyExecutionBoundaryError("Comfy execution request identity drifted")


def _sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()
