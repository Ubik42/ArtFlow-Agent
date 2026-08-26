import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from artflow_agent.agent_runtime import AgentEventStore, AgentRuntimeError
from artflow_agent.attestation import attest_local_capability
from artflow_agent.contracts import ProviderExecutionReceipt, RouteDecision, SceneConstraintPackage
from artflow_agent.contracts.provider import ProviderCapabilityManifest
from artflow_agent.domain import EnvironmentSnapshot, RecipeDefinition
from artflow_agent.provider_execution import (
    OfflineProviderSimulator,
    ProviderCompletionUnknown,
    ProviderExecutionCoordinator,
    ProviderExecutionError,
    SimulatedCoordinatorCrash,
)
from artflow_agent.scene_packages import ScenePackagePreview, VerifiedSceneArtifact


def _prepared_run(tmp_path: Path, *, approve: bool = True, attest: bool = True):
    payload = json.loads(
        (Path(__file__).parents[1] / "examples" / "scene-constraint-package.example.json").read_text(
            encoding="utf-8"
        )
    )
    package = SceneConstraintPackage.model_validate(payload)
    preview = ScenePackagePreview(
        package=package,
        archive_sha256="a" * 64,
        artifacts=[
            VerifiedSceneArtifact(
                path=item.artifact.path,
                sha256=item.artifact.sha256,
                size_bytes=10,
            )
            for item in package.passes
        ],
    )
    decision = RouteDecision(
        decision_id="route-execution-001",
        scene_package_id=package.package_id,
        scene_package_sha256=preview.archive_sha256,
        task="scene_direction",
        selected={
            "provider_id": "comfy-local",
            "model_id": "flux-local",
            "execution_kind": "local",
            "privacy_class": "local_only",
            "cost_class": "local_compute",
        },
        execution_intent={
            "required_controls": ["reference_image"],
            "evaluation_evidence": ["depth"],
            "output_count": 1,
            "width": package.camera.width,
            "height": package.camera.height,
            "delivery_format": "png",
            "intent_sha256": "b" * 64,
        },
        privacy_ceiling="local_only",
        max_cost_usd=0,
        requires_explicit_approval=True,
        rationale="Use the attested local fixture provider.",
    )
    database = tmp_path / "execution-events.sqlite3"
    store = AgentEventStore(database)
    store.create_run("execution-agent-run")
    store.attach_scene("execution-agent-run", preview)
    store.propose_route("execution-agent-run", decision)
    if attest:
        manifest = ProviderCapabilityManifest(
            provider_id="comfy-local",
            display_name="Fixture local",
            execution_kind="local",
            privacy_class="local_only",
            cost_class="local_compute",
            requires_explicit_cost_approval=False,
            models=[
                {
                    "model_id": "flux-local",
                    "model_version": "1",
                    "tasks": ["scene_direction"],
                    "controls": ["reference_image"],
                }
            ],
        )
        recipe = RecipeDefinition(
            recipe_id="fixture-recipe",
            version="1",
            task_type="scene_direction",
            description="fixture",
            workflow_file="fixture.json",
            execution_ready=True,
            consumed_controls=["reference_image"],
            required_models=["model.safetensors"],
            required_nodes=["LoadImage"],
            estimated_vram_mb=100,
            slots=[],
        )
        snapshot = EnvironmentSnapshot(
            comfy_url="http://127.0.0.1:8188",
            reachable=True,
            vram_mb=1000,
            nodes=["LoadImage"],
            models=["model.safetensors"],
        )
        store.record_capability_attestation(
            "execution-agent-run",
            attest_local_capability(snapshot, manifest, "flux-local", recipe),
        )
    if approve:
        store.resolve_route_approval("execution-agent-run", decision.decision_id, "approved")
    return database, decision


def test_submission_requires_approval_and_supported_attestation(tmp_path) -> None:
    database, decision = _prepared_run(tmp_path / "not-approved", approve=False)
    simulator = OfflineProviderSimulator()
    with pytest.raises(AgentRuntimeError, match="requires an approved persisted route"):
        ProviderExecutionCoordinator(AgentEventStore(database), simulator).run_or_reconcile(
            "execution-agent-run", "execution-001", "idem:execution-001", decision
        )
    assert simulator.submit_calls == 0

    database, decision = _prepared_run(tmp_path / "not-attested", attest=False)
    with pytest.raises(AgentRuntimeError, match="supported capability attestation"):
        ProviderExecutionCoordinator(AgentEventStore(database), simulator).run_or_reconcile(
            "execution-agent-run", "execution-001", "idem:execution-001", decision
        )
    assert simulator.submit_calls == 0


def test_crash_timeout_restart_and_terminal_reconciliation_do_not_resubmit(tmp_path) -> None:
    database, decision = _prepared_run(tmp_path)
    simulator = OfflineProviderSimulator()
    coordinator = ProviderExecutionCoordinator(AgentEventStore(database), simulator)

    with pytest.raises(SimulatedCoordinatorCrash):
        coordinator.run_or_reconcile(
            "execution-agent-run",
            "execution-001",
            "idem:execution-001",
            decision,
            crash_after_submit=True,
        )
    crashed = AgentEventStore(database).load("execution-agent-run")
    assert crashed.provider_executions[0].status == "reserved"
    assert simulator.submit_calls == 1

    unknown = ProviderExecutionCoordinator(
        AgentEventStore(database), simulator
    ).run_or_reconcile(
        "execution-agent-run", "execution-001", "idem:execution-001", decision
    )
    assert unknown.stage == "reconciling"
    assert unknown.provider_executions[0].status == "completion_unknown"
    assert simulator.submit_calls == 1

    simulator.succeed("idem:execution-001", {"artifacts/result.png": b"verified-result"})
    completed = ProviderExecutionCoordinator(
        AgentEventStore(database), simulator
    ).run_or_reconcile(
        "execution-agent-run", "execution-001", "idem:execution-001", decision
    )
    assert completed.stage == "execution_succeeded"
    assert completed.provider_executions[0].receipt is not None
    assert simulator.submit_calls == 1
    event_count = len(AgentEventStore(database).events("execution-agent-run"))

    replayed = ProviderExecutionCoordinator(
        AgentEventStore(database), simulator
    ).run_or_reconcile(
        "execution-agent-run", "execution-001", "idem:execution-001", decision
    )
    assert replayed == completed
    assert len(AgentEventStore(database).events("execution-agent-run")) == event_count
    assert simulator.submit_calls == 1


def test_ambiguous_submission_is_persisted_unknown_and_never_retried(tmp_path) -> None:
    database, decision = _prepared_run(tmp_path)

    class AmbiguousProvider:
        def __init__(self) -> None:
            self.submit_calls = 0

        def lookup(self, _idempotency_key):
            return None

        def submit(self, _request):
            self.submit_calls += 1
            raise ProviderCompletionUnknown("fixture_transport_completion_unknown")

        def fetch_artifact(self, _provider_request_id, _path):
            raise AssertionError("no artifact should be fetched")

    provider = AmbiguousProvider()
    coordinator = ProviderExecutionCoordinator(AgentEventStore(database), provider)
    unknown = coordinator.run_or_reconcile(
        "execution-agent-run", "execution-001", "idem:execution-001", decision
    )
    assert unknown.provider_executions[0].status == "completion_unknown"
    assert unknown.provider_executions[0].unknown_reason == (
        "fixture_transport_completion_unknown"
    )

    replayed = coordinator.run_or_reconcile(
        "execution-agent-run", "execution-001", "idem:execution-001", decision
    )
    assert replayed.provider_executions[0].status == "completion_unknown"
    assert provider.submit_calls == 1


def test_tampered_artifact_and_mismatched_receipt_never_become_success(tmp_path) -> None:
    database, decision = _prepared_run(tmp_path)
    simulator = OfflineProviderSimulator()
    coordinator = ProviderExecutionCoordinator(AgentEventStore(database), simulator)
    unknown = coordinator.run_or_reconcile(
        "execution-agent-run", "execution-001", "idem:execution-001", decision
    )
    assert unknown.stage == "reconciling"
    simulator.succeed("idem:execution-001", {"artifacts/result.png": b"original"})
    simulator.tamper_artifact("idem:execution-001", "artifacts/result.png", b"tampered")

    with pytest.raises(ProviderExecutionError, match="hash mismatch"):
        coordinator.run_or_reconcile(
            "execution-agent-run", "execution-001", "idem:execution-001", decision
        )
    assert AgentEventStore(database).load("execution-agent-run").stage == "reconciling"

    ledger = AgentEventStore(database).load("execution-agent-run").provider_executions[0]
    now = datetime.now(UTC)
    wrong = ProviderExecutionReceipt(
        execution_id=ledger.execution_id,
        route_decision_id=ledger.route_decision_id,
        route_fingerprint="f" * 64,
        provider_id=ledger.provider_id,
        model_id=ledger.model_id,
        status="failed",
        started_at=now,
        completed_at=now,
        provider_request_id=ledger.provider_request_id,
        error_code="fixture_failure",
    )
    with pytest.raises(AgentRuntimeError, match="fingerprint does not match"):
        AgentEventStore(database).record_provider_receipt("execution-agent-run", wrong)
