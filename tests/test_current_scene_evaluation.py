from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.web_api import create_app

RUN_ID = "unreal-artflow-ue-c4f262344b71ecfb5bf65580af4f5a1f-207d24a911c3"


def _database(tmp_path: Path) -> Path:
    root = Path(__file__).parents[1]
    source = root / "artifacts" / "goal" / "m12-s2-live-candidate-v2" / "agent-events.sqlite3"
    target = tmp_path / "agent-events.sqlite3"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _succeeded_work(
    tmp_path: Path, *, generated_instance_count: int = 12
) -> tuple[TestClient, Path, dict[str, object]]:
    database = _database(tmp_path)
    project_root = tmp_path / "project"
    client = TestClient(
        create_app(
            runs_dir=tmp_path / "runs",
            agent_database=database,
            project_root=project_root,
        ),
        client=("127.0.0.1", 51234),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-candidate-work"
    work = client.post(f"{base}/queue").json()["scene_candidate_work"]
    definition = work["definition"]
    plan = definition["candidate_plan"]
    output = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Saved/ArtFlowSceneBridge/SceneCandidates"
        / plan["plan_id"]
    )
    output.mkdir(parents=True)
    beauty = output / "candidate-beauty.png"
    Image.new("RGB", (640, 360), (88, 112, 132)).save(beauty)
    beauty_sha = hashlib.sha256(beauty.read_bytes()).hexdigest()
    source_sha = "4" * 64
    receipt = {
        "schema_id": "artflow-session-candidate-execution-receipt/1",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "stage_request_sha256": definition["stage_request"]["request_sha256"],
        "source_scene": plan["source_scene"],
        "source_level_sha256_before": source_sha,
        "source_level_sha256_after": source_sha,
        "source_level_unchanged": True,
        "candidate_scene": plan["candidate_destination"],
        "candidate_level_sha256": "5" * 64,
        "generated_instance_count": generated_instance_count,
        "reconciled": False,
        "candidate_beauty_path": str(beauty),
        "candidate_beauty_sha256": beauty_sha,
        "completed_at": "2026-08-30T12:00:00Z",
    }
    receipt_path = output / "candidate-execution-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    outcome = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    claim = {
        "schema_id": "artflow-scene-candidate-claim/1",
        "work_sha256": definition["work_sha256"],
        "session_sha256": definition["session_sha256"],
        "worker_id": "ue-editor-m20",
    }
    assert client.post(f"{base}/claim", json=claim).status_code == 200
    for status in ("executing", "reconciling"):
        assert client.post(
            f"{base}/progress",
            json={
                "schema_id": "artflow-scene-candidate-progress/1",
                "work_sha256": definition["work_sha256"],
                "worker_id": "ue-editor-m20",
                "status": status,
                "action_id": f"m20-{status}",
            },
        ).status_code == 200
    assert client.post(
        f"{base}/progress",
        json={
            "schema_id": "artflow-scene-candidate-progress/1",
            "work_sha256": definition["work_sha256"],
            "worker_id": "ue-editor-m20",
            "status": "succeeded",
            "action_id": "m20-succeeded",
            "outcome_sha256": outcome,
        },
    ).status_code == 200
    return client, database, work


def test_current_candidate_intake_is_content_bound_idempotent_and_replayable(
    tmp_path: Path,
) -> None:
    client, database, work = _succeeded_work(tmp_path)
    endpoint = f"/api/agent/runs/{RUN_ID}/scene-candidate-work/evaluate"

    first = client.post(endpoint)
    replay = client.post(endpoint)
    assert first.status_code == replay.status_code == 200
    intake = first.json()["scene_candidate_intake"]
    assert intake == replay.json()["scene_candidate_intake"]
    assert intake["technical_evaluation"]["status"] == "eligible_for_visual_review"
    assert intake["technical_evaluation"]["failed_domains"] == []
    assert len(intake["technical_evaluation"]["checks"]) == 6
    assert intake["evaluation_input"]["work_sha256"] == work["definition"]["work_sha256"]
    assert len(AgentEventStore(database).events(RUN_ID)) == 9

    restored = AgentEventStore(database).load(RUN_ID).scene_candidate_intake
    assert restored is not None
    assert restored == AgentEventStore(database).load(RUN_ID).scene_candidate_intake
    assert restored.technical_evaluation.status == "eligible_for_visual_review"


def test_current_candidate_intake_rejects_failed_pcg_budget_without_visual_override(
    tmp_path: Path,
) -> None:
    client, _, _ = _succeeded_work(tmp_path, generated_instance_count=999)
    response = client.post(
        f"/api/agent/runs/{RUN_ID}/scene-candidate-work/evaluate"
    )
    assert response.status_code == 200
    evaluation = response.json()["scene_candidate_intake"]["technical_evaluation"]
    assert evaluation["status"] == "rejected"
    assert evaluation["failed_domains"] == ["pcg"]
    budget = next(check for check in evaluation["checks"] if check["check_id"] == "instance_budget")
    assert budget["status"] == "failed"
