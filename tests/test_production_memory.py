import sqlite3
from pathlib import Path

import pytest

from artflow_agent.agent_runtime import AgentEventStore, AgentRuntimeError
from artflow_agent.production_memory import (
    MemoryQuery,
    build_memory_proposal,
    retrieve_memory,
)

ROOT = Path(__file__).parents[1]
SOURCE_DATABASE = (
    ROOT / "artifacts" / "goal" / "m3-s11-local-run" / "agent-events.sqlite3"
)
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def _store(tmp_path: Path) -> tuple[AgentEventStore, str, str]:
    database = tmp_path / "events.sqlite3"
    with sqlite3.connect(SOURCE_DATABASE) as source, sqlite3.connect(database) as target:
        source.backup(target)
    store = AgentEventStore(database)
    state = store.load(RUN_ID)
    assert state.scene is not None
    return store, state.scene.package.package_id, store.events(RUN_ID)[-1].event_hash


def _proposal(project_id: str, source_hash: str, **overrides):
    data = {
        "memory_id": "memory-camera-rule-v1",
        "kind": "semantic",
        "project_id": project_id,
        "subject_key": "test.scene.camera.preserve",
        "value": "保持已验证机位、画幅与主体剪影。",
        "tags": ["camera", "constraint"],
        "version": 1,
        "source_run_id": RUN_ID,
        "source_event_hashes": [source_hash],
    }
    data.update(overrides)
    return build_memory_proposal(**data)


def test_project_memory_activates_replays_and_retrieves_exact_citations(tmp_path) -> None:
    store, project_id, source_hash = _store(tmp_path)
    proposal = _proposal(project_id, source_hash)
    proposed = store.propose_memory(RUN_ID, proposal)
    assert proposed.memory_records[-1].status == "proposed"
    active = store.resolve_memory(RUN_ID, proposal.memory_id)
    assert active.memory_records[-1].status == "active"
    event_count = len(store.events(RUN_ID))

    store.propose_memory(RUN_ID, proposal)
    replayed = store.resolve_memory(RUN_ID, proposal.memory_id)
    assert len(store.events(RUN_ID)) == event_count
    assert AgentEventStore(store.database_path).load(RUN_ID) == replayed

    result = retrieve_memory(
        replayed.memory_records,
        MemoryQuery(
            project_id=project_id,
            kinds=["semantic"],
            subject_keys=["test.scene.camera.preserve"],
            tags=["camera"],
        ),
    )
    assert [item.memory_id for item in result.citations] == [proposal.memory_id]
    assert result.citations[0].source_event_hashes == [source_hash]


def test_memory_policy_rejects_shared_stale_conflict_and_forged_sources(tmp_path) -> None:
    store, project_id, source_hash = _store(tmp_path)
    first = _proposal(project_id, source_hash)
    store.propose_memory(RUN_ID, first)
    store.resolve_memory(RUN_ID, first.memory_id)

    shared = _proposal(
        project_id,
        source_hash,
        memory_id="memory-shared-rule-v1",
        subject_key="scene.shared.rule",
        target_scope="shared",
    )
    store.propose_memory(RUN_ID, shared)
    shared_state = store.resolve_memory(RUN_ID, shared.memory_id)
    shared_record = shared_state.memory_records[-1]
    assert shared_record.status == "rejected"
    assert shared_record.policy_decision is not None
    assert shared_record.policy_decision.reason_codes == ["shared_scope_authority_missing"]

    stale = _proposal(
        project_id,
        source_hash,
        memory_id="memory-camera-stale-v1",
    )
    store.propose_memory(RUN_ID, stale)
    assert store.resolve_memory(RUN_ID, stale.memory_id).memory_records[-1].status == "rejected"

    conflict = _proposal(
        project_id,
        source_hash,
        memory_id="memory-camera-rule-v2",
        version=2,
        value="改变现有机位。",
    )
    store.propose_memory(RUN_ID, conflict)
    conflict_state = store.resolve_memory(RUN_ID, conflict.memory_id)
    assert conflict_state.memory_records[-1].policy_decision is not None
    assert conflict_state.memory_records[-1].policy_decision.reason_codes == [
        "conflict_requires_explicit_supersession"
    ]

    forged = _proposal(
        project_id,
        "f" * 64,
        memory_id="memory-forged-rule-v1",
        subject_key="scene.forged.rule",
    )
    with pytest.raises(AgentRuntimeError, match="forged or missing"):
        store.propose_memory(RUN_ID, forged)


def test_contiguous_supersession_preserves_lineage_and_filters_irrelevant_memory(
    tmp_path,
) -> None:
    store, project_id, source_hash = _store(tmp_path)
    first = _proposal(project_id, source_hash)
    store.propose_memory(RUN_ID, first)
    store.resolve_memory(RUN_ID, first.memory_id)
    second = _proposal(
        project_id,
        source_hash,
        memory_id="memory-camera-rule-v2",
        version=2,
        value="保持已验证机位；仅允许遮罩内光照细化。",
        supersedes_memory_id=first.memory_id,
    )
    store.propose_memory(RUN_ID, second)
    state = store.resolve_memory(RUN_ID, second.memory_id)
    by_id = {record.proposal.memory_id: record for record in state.memory_records}
    assert by_id[first.memory_id].status == "superseded"
    assert by_id[first.memory_id].superseded_by_memory_id == second.memory_id
    assert by_id[second.memory_id].status == "active"

    irrelevant = retrieve_memory(
        state.memory_records,
        MemoryQuery(project_id=project_id, tags=["unrelated"]),
    )
    assert irrelevant.citations == []
