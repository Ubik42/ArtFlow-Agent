import hashlib
import json
import sqlite3
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi.testclient import TestClient

from artflow_agent.agent_harness import OfflineCoordinator, build_offline_registry
from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.comparison import ProviderComparisonPlan
from artflow_agent.scene_packages import ScenePackageArchive
from artflow_agent.web_api import create_app


def _agent_database(tmp_path: Path) -> Path:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "examples" / "scene-constraint-package.example.json").read_text(
            encoding="utf-8"
        )
    )
    artifacts = {
        "passes/beauty.png": b"beauty",
        "passes/depth.exr": b"depth",
        "passes/world-normal.exr": b"world-normal",
        "passes/object-id.png": b"object-id",
    }
    for item in manifest["passes"]:
        item["artifact"]["sha256"] = hashlib.sha256(
            artifacts[item["artifact"]["path"]]
        ).hexdigest()
    archive_path = tmp_path / "scene.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("scene-package.json", json.dumps(manifest))
        for name, content in artifacts.items():
            archive.writestr(name, content)

    database = tmp_path / "agent-events.sqlite3"
    store = AgentEventStore(database)
    store.create_run("scene-lab-run")
    store.attach_scene("scene-lab-run", ScenePackageArchive().inspect(archive_path))
    OfflineCoordinator(store, build_offline_registry()).run_once("scene-lab-run")
    return database


def _ui_comparison_plan(scene_sha256: str) -> ProviderComparisonPlan:
    common = {
        "comparison_id": "scene-lab-run",
        "dossier_id": "launch-dossier",
        "dossier_sha256": "d" * 64,
        "scene_package_id": "coastal-ruins-ue-capture-001",
        "scene_package_sha256": scene_sha256,
        "art_intent_sha256": "b" * 64,
        "operator_preview": {
            "local_uploads": ["beauty"],
            "hosted_uploads": ["beauty"],
            "hosted_endpoint": "/v1/images/edits",
            "hosted_model": "gpt-image-2-2026-04-21",
            "output_count_per_provider": 1,
            "output_size": "1280x720",
            "estimated_hosted_cost_usd": 0.10,
            "maximum_hosted_cost_usd": 0.25,
            "hosted_privacy_class": "provider_retained",
            "cost_cap_provider_enforced": False,
            "unresolved_real_host_facts": ["Real host execution is not authorized."],
        },
    }
    children = [
        {
            "role": "local",
            "action_id": "local-comfy-generation",
            "run_id": "local-child-run",
            "execution_id": "local-child-execution",
            "idempotency_key": "comparison:scene:local",
            "provider_id": "comfy-local",
            "model_id": "flux-2-klein-base-4b-fp8",
            "route_decision_id": "route-local",
            "route_fingerprint": "1" * 64,
            "attestation_environment_sha256": "2" * 64,
            "authority_kind": "bounded_local_compute",
        },
        {
            "role": "hosted",
            "action_id": "hosted-openai-edit",
            "run_id": "hosted-child-run",
            "execution_id": "hosted-child-execution",
            "idempotency_key": "comparison:scene:hosted",
            "provider_id": "openai-images",
            "model_id": "gpt-image-2-2026-04-21",
            "route_decision_id": "route-hosted",
            "route_fingerprint": "3" * 64,
            "attestation_environment_sha256": "4" * 64,
            "authority_kind": "hosted_privacy_cost",
        },
    ]
    return ProviderComparisonPlan.model_validate({**common, "children": children})


def test_agent_projection_is_compact_typed_and_replay_backed(tmp_path) -> None:
    database = _agent_database(tmp_path)
    client = TestClient(create_app(runs_dir=tmp_path / "legacy", agent_database=database))

    summaries = client.get("/api/agent/runs")
    response = client.get("/api/agent/runs/scene-lab-run")

    assert summaries.status_code == 200
    assert summaries.json()[0]["last_sequence"] == 5
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_id"] == "agent-run-projection/1"
    assert payload["scene"]["source_scene"] == "CoastalRuins"
    assert payload["status"]["budgets"]["used_tool_calls"] == 1
    assert payload["timeline"][-1]["event_type"] == "tool_observed"
    assert payload["capabilities"][0]["authority"]["reads"] == ["agent_state.scene"]
    serialized = response.text
    assert "previous_hash" not in serialized
    assert "data_json" not in serialized
    assert len(serialized) < 30_000


def test_unknown_and_corrupt_agent_runs_are_explicit(tmp_path) -> None:
    database = _agent_database(tmp_path)
    client = TestClient(create_app(runs_dir=tmp_path / "legacy", agent_database=database))
    assert client.get("/api/agent/runs/missing-run").status_code == 404

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_events SET data_json = ? WHERE run_id = ? AND sequence = 1",
            ('{"tampered":true}', "scene-lab-run"),
        )
        connection.commit()

    corrupted = client.get("/api/agent/runs/scene-lab-run")
    assert corrupted.status_code == 409
    assert "hash does not match" in corrupted.json()["detail"]


def test_sse_replay_and_route_approval_are_durable(tmp_path) -> None:
    database = _agent_database(tmp_path)
    store = AgentEventStore(database)
    store.request_route_approval(
        "scene-lab-run",
        "route-local-reviewed",
        "Use the reviewed local ComfyUI route; no external upload or provider cost.",
        fingerprint="b" * 64,
    )
    client = TestClient(create_app(runs_dir=tmp_path / "legacy", agent_database=database))

    stream = client.get("/api/agent/runs/scene-lab-run/stream?after=3&follow=false")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "schema_id\":\"agent-ui-event/1" in stream.text
    assert "event: run.event" in stream.text
    assert "event: interrupt" in stream.text
    assert "id: 6" in stream.text
    assert "previous_hash" not in stream.text

    approved = client.post(
        "/api/agent/runs/scene-lab-run/approvals/route-local-reviewed",
        json={"resolution": "approved"},
    )
    assert approved.status_code == 200
    assert approved.json()["stage"] == "approved"
    reopened = AgentEventStore(database).load("scene-lab-run")
    assert reopened.approval == "approved"
    assert reopened.pending_decisions == []


def test_route_rejection_returns_run_to_route_ready(tmp_path) -> None:
    database = _agent_database(tmp_path)
    store = AgentEventStore(database)
    store.request_route_approval("scene-lab-run", "route-reject", "Reject this route")
    client = TestClient(create_app(runs_dir=tmp_path / "legacy", agent_database=database))

    rejected = client.post(
        "/api/agent/runs/scene-lab-run/approvals/route-reject",
        json={"resolution": "rejected"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["stage"] == "route_ready"
    assert rejected.json()["approval"] == "rejected"


def test_comparison_projection_stream_and_dedicated_authorization_are_durable(
    tmp_path,
) -> None:
    database = _agent_database(tmp_path)
    store = AgentEventStore(database)
    state = store.load("scene-lab-run")
    assert state.scene is not None
    plan = _ui_comparison_plan(state.scene.archive_sha256)
    store.record_comparison_plan("scene-lab-run", plan)
    client = TestClient(create_app(runs_dir=tmp_path / "legacy", agent_database=database))

    projection = client.get("/api/agent/runs/scene-lab-run").json()
    assert projection["comparison_plan"]["operator_preview"]["hosted_uploads"] == [
        "beauty"
    ]
    assert projection["pending_decisions"][0]["kind"] == "comparison_authorization"
    bypass = client.post(
        "/api/agent/runs/scene-lab-run/approvals/authorize-scene-lab-run",
        json={"resolution": "approved"},
    )
    assert bypass.status_code == 409

    approved = client.post(
        "/api/agent/runs/scene-lab-run/comparison/authorize",
        json={"approved_by": "portfolio-owner"},
    )
    assert approved.status_code == 200
    payload = approved.json()
    assert payload["comparison_authorization"]["authorized_action_ids"] == [
        "hosted-openai-edit",
    ]
    assert payload["pending_decisions"] == []

    duplicate = client.post(
        "/api/agent/runs/scene-lab-run/comparison/authorize",
        json={"approved_by": "portfolio-owner"},
    )
    assert duplicate.status_code == 200
    assert len(AgentEventStore(database).events("scene-lab-run")) == 7
    stream = client.get(
        "/api/agent/runs/scene-lab-run/stream?after=5&follow=false"
    )
    assert "comparison_planned" in stream.text
    assert "comparison_authorized" in stream.text
    assert "hosted_privacy_cost" in stream.text
