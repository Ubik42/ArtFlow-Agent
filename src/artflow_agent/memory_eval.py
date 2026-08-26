from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .agent_runtime import AgentEventStore, AgentRuntimeError
from .production_memory import (
    MemoryEvalCase,
    MemoryQuery,
    MemoryScorecard,
    build_memory_proposal,
    retrieve_memory,
)


def run_frozen_memory_suite(
    output_dir: Path,
    *,
    source_database: Path,
    run_id: str,
) -> MemoryScorecard:
    output_dir.mkdir(parents=True, exist_ok=True)
    database = output_dir / "memory-eval-events.sqlite3"
    for stale in (
        database,
        database.with_name(database.name + "-wal"),
        database.with_name(database.name + "-shm"),
    ):
        stale.unlink(missing_ok=True)
    with sqlite3.connect(source_database) as source, sqlite3.connect(database) as target:
        source.backup(target)
    store = AgentEventStore(database)
    state = store.load(run_id)
    if state.scene is None:
        raise RuntimeError("Memory evaluation requires a scene-bound run")
    project_id = state.scene.package.package_id
    source_hash = store.events(run_id)[-1].event_hash
    cases: list[MemoryEvalCase] = []

    valid = build_memory_proposal(
        memory_id="memory-eval-camera-v1",
        kind="semantic",
        project_id=project_id,
        subject_key="eval.scene.camera.preserve",
        value="保持已验证机位。",
        tags=["camera", "constraint"],
        version=1,
        source_run_id=run_id,
        source_event_hashes=[source_hash],
    )
    started = time.perf_counter()
    store.propose_memory(run_id, valid)
    activated = store.resolve_memory(run_id, valid.memory_id)
    count = len(store.events(run_id))
    store.propose_memory(run_id, valid)
    store.resolve_memory(run_id, valid.memory_id)
    cases.append(
        _case(
            "activation_restart_replay",
            activated.memory_records[-1].status == "active"
            and len(store.events(run_id)) == count
            and AgentEventStore(database).load(run_id).memory_records[-1].status == "active",
            "active_without_duplicate_events",
            f"{activated.memory_records[-1].status};events={len(store.events(run_id)) - count}",
            started,
            [valid.memory_id],
        )
    )

    conflict = build_memory_proposal(
        memory_id="memory-eval-camera-v2",
        kind="semantic",
        project_id=project_id,
        subject_key="eval.scene.camera.preserve",
        value="改变机位。",
        tags=["camera", "constraint"],
        version=2,
        source_run_id=run_id,
        source_event_hashes=[source_hash],
    )
    cases.append(_resolve_case(store, run_id, conflict, "conflict_rejection", "conflict_requires_explicit_supersession"))

    stale = build_memory_proposal(
        memory_id="memory-eval-camera-stale",
        kind="semantic",
        project_id=project_id,
        subject_key="eval.scene.camera.preserve",
        value="旧版机位规则。",
        tags=["camera", "constraint"],
        version=1,
        source_run_id=run_id,
        source_event_hashes=[source_hash],
    )
    cases.append(_resolve_case(store, run_id, stale, "stale_version_rejection", "stale_version"))

    shared = build_memory_proposal(
        memory_id="memory-eval-shared-v1",
        kind="procedural",
        project_id=project_id,
        subject_key="revision.shared.playbook",
        value="将项目规则提升为共享规则。",
        tags=["revision", "privacy"],
        version=1,
        source_run_id=run_id,
        source_event_hashes=[source_hash],
        target_scope="shared",
    )
    cases.append(_resolve_case(store, run_id, shared, "private_promotion_rejection", "shared_scope_authority_missing"))

    forged_started = time.perf_counter()
    forged = build_memory_proposal(
        memory_id="memory-eval-forged-v1",
        kind="episodic",
        project_id=project_id,
        subject_key="run.forged.fact",
        value="不存在的运行事实。",
        tags=["forged"],
        version=1,
        source_run_id=run_id,
        source_event_hashes=["f" * 64],
    )
    observed = "accepted"
    try:
        store.propose_memory(run_id, forged)
    except AgentRuntimeError:
        observed = "forged_source_rejected"
    cases.append(
        _case(
            "forged_source_rejection",
            observed == "forged_source_rejected",
            "forged_source_rejected",
            observed,
            forged_started,
        )
    )

    retrieval_started = time.perf_counter()
    relevant = retrieve_memory(
        store.load(run_id).memory_records,
        MemoryQuery(
            project_id=project_id,
            subject_keys=["eval.scene.camera.preserve"],
            tags=["camera"],
        ),
    )
    irrelevant = retrieve_memory(
        store.load(run_id).memory_records,
        MemoryQuery(project_id=project_id, tags=["unrelated"]),
    )
    retrieval_passed = (
        [item.memory_id for item in relevant.citations] == [valid.memory_id]
        and irrelevant.citations == []
    )
    cases.append(
        _case(
            "irrelevant_retrieval_filter",
            retrieval_passed,
            "one_exact_citation_and_zero_irrelevant",
            f"relevant={len(relevant.citations)};irrelevant={len(irrelevant.citations)}",
            retrieval_started,
            [item.memory_id for item in relevant.citations],
        )
    )
    scorecard = MemoryScorecard(
        passed_cases=sum(case.passed for case in cases),
        total_cases=len(cases),
        retrieval_precision=1.0 if retrieval_passed else 0.0,
        conflict_rejection_rate=(
            sum(case.passed for case in cases[1:5]) / 4
        ),
        total_latency_ms=round(sum(case.latency_ms for case in cases), 3),
        cases=cases,
        limitations=[
            "The suite uses deterministic metadata retrieval; semantic recall is not claimed.",
            "All policy cases run against a local SQLite backup of the real event chain.",
            "Shared-scope activation has no authority contract and is intentionally rejected.",
        ],
    )
    (output_dir / "memory-scorecard.json").write_text(
        scorecard.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return scorecard


def _resolve_case(store, run_id, proposal, case_id, expected_reason) -> MemoryEvalCase:
    started = time.perf_counter()
    store.propose_memory(run_id, proposal)
    state = store.resolve_memory(run_id, proposal.memory_id)
    record = next(
        item for item in state.memory_records if item.proposal.memory_id == proposal.memory_id
    )
    observed = (
        record.policy_decision.reason_codes[0]
        if record.policy_decision is not None
        else "missing_decision"
    )
    return _case(
        case_id,
        record.status == "rejected" and observed == expected_reason,
        expected_reason,
        observed,
        started,
        [proposal.memory_id],
    )


def _case(
    case_id: str,
    passed: bool,
    expected: str,
    observed: str,
    started: float,
    evidence_memory_ids: list[str] | None = None,
) -> MemoryEvalCase:
    return MemoryEvalCase(
        case_id=case_id,
        passed=passed,
        expected=expected,
        observed=observed,
        latency_ms=round((time.perf_counter() - started) * 1000, 3),
        evidence_memory_ids=evidence_memory_ids or [],
    )
