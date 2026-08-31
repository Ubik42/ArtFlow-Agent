from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from artflow_agent.agent_runtime import AgentEventStore, AgentRuntimeError
from artflow_agent.scene_variant_lifecycle import load_registered_m16_lifecycle
from artflow_agent.web_api import create_app


RUN_ID = "unreal-artflow-ue-c4f262344b71ecfb5bf65580af4f5a1f-207d24a911c3"


def _database(tmp_path: Path) -> Path:
    root = Path(__file__).parents[1]
    source = root / "artifacts" / "goal" / "m12-s2-live-candidate-v2" / "agent-events.sqlite3"
    target = tmp_path / "agent-events.sqlite3"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _record_all(store: AgentEventStore, root: Path) -> None:
    registered = load_registered_m16_lifecycle(root)
    store.record_scene_candidate_evaluation(
        RUN_ID, registered.evaluation, action_id="m16-evaluation-445666ae184f"
    )
    store.record_scene_candidate_adoption(
        RUN_ID, registered.adoption, action_id="m16-adoption-a9d761a38175"
    )
    store.record_scene_variant_publication(
        RUN_ID, registered.publication, action_id="m16-publish-a38499432ad2"
    )
    store.record_scene_variant_review(
        RUN_ID, registered.review, action_id="m16-review-e9f219a423c2"
    )


def test_lifecycle_replays_exactly_and_rejects_changed_idempotent_input(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    database = _database(tmp_path)
    store = AgentEventStore(database)
    _record_all(store, root)
    _record_all(store, root)

    assert len(store.events(RUN_ID)) == 7
    reopened = AgentEventStore(database).load(RUN_ID)
    assert reopened.scene_candidate_evaluation is not None
    assert reopened.scene_candidate_adoption is not None
    assert reopened.scene_variant_publication is not None
    assert reopened.scene_variant_review is not None
    assert reopened.scene_variant_review.lineage.review_status == "reconciled"
    assert reopened.scene_variant_review.lineage.generated_instance_count == 12

    registered = load_registered_m16_lifecycle(root)
    changed_lineage = registered.review.lineage.model_copy(
        update={"published_level_sha256": "f" * 64}
    )
    changed_review = registered.review.model_copy(update={"lineage": changed_lineage})
    with pytest.raises(AgentRuntimeError, match="Idempotency key"):
        store.record_scene_variant_review(
            RUN_ID, changed_review, action_id="m16-review-e9f219a423c2"
        )


def test_lifecycle_rejects_another_persisted_session(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    store = AgentEventStore(_database(tmp_path))
    registered = load_registered_m16_lifecycle(root)
    other_run = "unreal-artflow-ue-3a008cc64df886f25340d88d63cc9a6b-4507d145f06b"
    with pytest.raises(AgentRuntimeError, match="another run"):
        store.record_scene_candidate_evaluation(
            other_run, registered.evaluation, action_id="m16-evaluation-foreign"
        )


def test_loopback_registration_returns_live_projection_without_path_input(tmp_path: Path) -> None:
    database = _database(tmp_path)
    client = TestClient(
        create_app(runs_dir=tmp_path / "runs", agent_database=database),
        client=("127.0.0.1", 51234),
    )
    url = f"/api/agent/runs/{RUN_ID}/scene-variant-lifecycle/m16"
    first = client.post(url)
    replay = client.post(url)

    assert first.status_code == 200
    assert replay.status_code == 200
    assert first.json()["scene_variant_lineage"] == replay.json()["scene_variant_lineage"]
    assert first.json()["scene_variant_lineage"]["published_scene"].startswith(
        "/Game/ArtFlow/Published/AF_784907467248/"
    )
    assert first.json()["timeline"][-1]["event_type"] == "scene_variant_reviewed"

    remote = TestClient(
        create_app(runs_dir=tmp_path / "remote", agent_database=_database(tmp_path / "remote-db")),
        client=("203.0.113.10", 51234),
    )
    assert remote.post(url).status_code == 403
