from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path

from .agent_runtime import AgentEventStore
from .attestation import attest_local_capability
from .contracts import RouteDecision, SceneConstraintPackage
from .contracts.provider import ProviderCapabilityManifest
from .domain import EnvironmentSnapshot, RecipeDefinition
from .observability import TraceRecorder
from .provider_execution import (
    OfflineProviderSimulator,
    ProviderCompletionUnknown,
    ProviderExecutionCoordinator,
    SimulatedCoordinatorCrash,
)
from .recovery_contracts import RecoveryCaseResult, RecoveryScorecard
from .scene_packages import ScenePackagePreview, VerifiedSceneArtifact

FROZEN_MATRIX_VERSION = "m5-s1-recovery-matrix/1"
FROZEN_CASES = (
    "before_reservation",
    "after_reservation",
    "after_submit",
    "completion_unknown",
    "after_artifact_persistence_before_event_commit",
    "adoption_revision_replay",
)


def run_frozen_recovery_matrix(
    output_dir: Path,
    *,
    project_root: Path,
    production_database: Path,
    production_run_id: str,
) -> RecoveryScorecard:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        _provider_case(output_dir, project_root, case_id)
        for case_id in FROZEN_CASES[:-1]
    ]
    cases.append(
        _adoption_revision_replay_case(
            output_dir,
            production_database=production_database,
            production_run_id=production_run_id,
        )
    )
    scorecard = RecoveryScorecard(
        matrix_version=FROZEN_MATRIX_VERSION,
        generated_at=datetime.now(UTC),
        passed_cases=sum(case.passed for case in cases),
        total_cases=len(FROZEN_CASES),
        duplicate_side_effect_count=sum(
            case.duplicate_side_effect_count for case in cases
        ),
        recovery_latency_ms_total=round(
            sum(case.recovery_latency_ms for case in cases), 3
        ),
        cases=cases,
        limitations=[
            "All failures use deterministic local fixtures; no live provider outage was induced.",
            "Latency is local restart/reconciliation wall time, not production network latency.",
            "Completion-unknown intentionally remains non-terminal until provider evidence appears.",
        ],
    )
    (output_dir / "recovery-scorecard.json").write_text(
        scorecard.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return scorecard


def _provider_case(
    output_dir: Path,
    project_root: Path,
    case_id: str,
) -> RecoveryCaseResult:
    case_dir = output_dir / "cases" / case_id
    database, decision = _prepared_run(case_dir, project_root)
    trace_path = output_dir / "traces" / f"{case_id}.json"
    trace = TraceRecorder(trace_path)
    provider = _UnknownCompletionProvider() if case_id == "completion_unknown" else OfflineProviderSimulator()
    run_id = "recovery-agent-run"
    execution_id = "execution-001"
    idempotency_key = "idem:execution-001"
    started = time.perf_counter()
    outcome = ""
    try:
        coordinator = ProviderExecutionCoordinator(AgentEventStore(database), provider, trace)
        if case_id in {"before_reservation", "after_reservation", "after_submit"}:
            try:
                coordinator.run_or_reconcile(
                    run_id,
                    execution_id,
                    idempotency_key,
                    decision,
                    inject_failure_at=case_id,
                )
            except SimulatedCoordinatorCrash:
                pass
            coordinator = ProviderExecutionCoordinator(AgentEventStore(database), provider, trace)
            coordinator.run_or_reconcile(run_id, execution_id, idempotency_key, decision)
            provider.succeed(idempotency_key, {"artifacts/result.png": b"verified-result"})
            final = coordinator.run_or_reconcile(
                run_id, execution_id, idempotency_key, decision
            )
            outcome = final.stage
        elif case_id == "completion_unknown":
            coordinator.run_or_reconcile(run_id, execution_id, idempotency_key, decision)
            final = coordinator.run_or_reconcile(
                run_id, execution_id, idempotency_key, decision
            )
            outcome = final.provider_executions[0].status
        else:
            coordinator.run_or_reconcile(run_id, execution_id, idempotency_key, decision)
            provider.succeed(idempotency_key, {"artifacts/result.png": b"persisted-result"})
            try:
                coordinator.run_or_reconcile(
                    run_id,
                    execution_id,
                    idempotency_key,
                    decision,
                    inject_failure_at="after_artifact_verification",
                )
            except SimulatedCoordinatorCrash:
                pass
            final = ProviderExecutionCoordinator(
                AgentEventStore(database), provider, trace
            ).run_or_reconcile(run_id, execution_id, idempotency_key, decision)
            outcome = final.stage
    finally:
        trace.shutdown()

    events = AgentEventStore(database).events(run_id)
    terminal_count = sum(event.event_type == "provider_receipt_recorded" for event in events)
    submit_count = provider.submit_calls
    expected_terminal_count = 0 if case_id == "completion_unknown" else 1
    passed = submit_count == 1 and terminal_count == expected_terminal_count
    if case_id == "completion_unknown":
        passed = passed and outcome == "completion_unknown"
    else:
        passed = passed and outcome == "execution_succeeded"
    return RecoveryCaseResult(
        case_id=case_id,
        passed=passed,
        recovery_outcome=outcome,
        provider_side_effect_count=submit_count,
        terminal_event_count=terminal_count,
        duplicate_side_effect_count=max(0, submit_count - 1) + max(0, terminal_count - 1),
        recovery_latency_ms=round((time.perf_counter() - started) * 1000, 3),
        trace_path=trace_path.relative_to(output_dir).as_posix(),
        event_database_path=database.relative_to(output_dir).as_posix(),
        final_event_sequence=events[-1].sequence,
        evidence_event_hashes=[event.event_hash for event in events[-3:]],
        limitation=(
            "Safe unresolved boundary; absence of provider evidence forbids automatic resubmission."
            if case_id == "completion_unknown"
            else None
        ),
    )


def _adoption_revision_replay_case(
    output_dir: Path,
    *,
    production_database: Path,
    production_run_id: str,
) -> RecoveryCaseResult:
    case_dir = output_dir / "cases" / "adoption_revision_replay"
    case_dir.mkdir(parents=True, exist_ok=True)
    database = case_dir / "agent-events.sqlite3"
    _remove_sqlite_files(database)
    with sqlite3.connect(production_database) as source, sqlite3.connect(database) as target:
        source.backup(target)
    store = AgentEventStore(database)
    state = store.load(production_run_id)
    if not (
        state.adoption_decision
        and state.bounded_revision_request
        and state.bounded_revision_result
    ):
        raise RuntimeError("Production evidence lacks adoption or bounded revision state")
    started = time.perf_counter()
    before = store.events(production_run_id)
    store.record_candidate_adoption(production_run_id, state.adoption_decision)
    store.record_bounded_revision_request(production_run_id, state.bounded_revision_request)
    attempts = state.bounded_revision_attempts
    store.record_bounded_revision_result(production_run_id, state.bounded_revision_result)
    store.record_bounded_revision_correction(production_run_id, state.bounded_revision_result)
    after = store.events(production_run_id)
    adoption_count = sum(event.event_type == "production_candidate_adopted" for event in after)
    revision_count = len(
        {attempt.receipt.raw_artifact_sha256 for attempt in attempts}
    )
    revision_event_count = sum(
        event.event_type in {"bounded_revision_recorded", "bounded_revision_corrected"}
        for event in after
    )
    passed = (
        len(before) == len(after)
        and adoption_count == 1
        and revision_count == 1
        and revision_event_count == len(attempts)
    )
    return RecoveryCaseResult(
        case_id="adoption_revision_replay",
        passed=passed,
        recovery_outcome="idempotent_replay",
        provider_side_effect_count=1,
        adoption_side_effect_count=adoption_count,
        revision_side_effect_count=revision_count,
        terminal_event_count=1,
        duplicate_side_effect_count=max(0, len(after) - len(before)),
        recovery_latency_ms=round((time.perf_counter() - started) * 1000, 3),
        event_database_path=database.relative_to(output_dir).as_posix(),
        final_event_sequence=after[-1].sequence,
        evidence_event_hashes=[
            event.event_hash
            for event in after
            if event.event_type
            in {
                "production_candidate_adopted",
                "bounded_revision_requested",
                "bounded_revision_recorded",
                "bounded_revision_corrected",
            }
        ],
        limitation="Replays the persisted real-run ledger on a SQLite backup; it does not regenerate media.",
    )


def _prepared_run(case_dir: Path, project_root: Path) -> tuple[Path, RouteDecision]:
    case_dir.mkdir(parents=True, exist_ok=True)
    package = SceneConstraintPackage.model_validate_json(
        (project_root / "examples" / "scene-constraint-package.example.json").read_text(
            encoding="utf-8"
        )
    )
    preview = ScenePackagePreview(
        package=package,
        archive_sha256="a" * 64,
        artifacts=[
            VerifiedSceneArtifact(path=item.artifact.path, sha256=item.artifact.sha256, size_bytes=10)
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
    database = case_dir / "agent-events.sqlite3"
    _remove_sqlite_files(database)
    store = AgentEventStore(database)
    run_id = "recovery-agent-run"
    store.create_run(run_id)
    store.attach_scene(run_id, preview)
    store.propose_route(run_id, decision)
    manifest = ProviderCapabilityManifest(
        provider_id="comfy-local",
        display_name="Fixture local",
        execution_kind="local",
        privacy_class="local_only",
        cost_class="local_compute",
        requires_explicit_cost_approval=False,
        models=[{
            "model_id": "flux-local",
            "model_version": "1",
            "tasks": ["scene_direction"],
            "controls": ["reference_image"],
        }],
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
        run_id, attest_local_capability(snapshot, manifest, "flux-local", recipe)
    )
    store.resolve_route_approval(run_id, decision.decision_id, "approved")
    return database, decision


class _UnknownCompletionProvider:
    def __init__(self) -> None:
        self.submit_calls = 0

    def lookup(self, _idempotency_key: str):
        return None

    def submit(self, _request):
        self.submit_calls += 1
        raise ProviderCompletionUnknown("fixture_transport_completion_unknown")

    def fetch_artifact(self, _provider_request_id: str, _path: str) -> bytes:
        raise AssertionError("No artifact should be fetched")


def _remove_sqlite_files(database: Path) -> None:
    for stale in (
        database,
        database.with_name(database.name + "-wal"),
        database.with_name(database.name + "-shm"),
    ):
        stale.unlink(missing_ok=True)
