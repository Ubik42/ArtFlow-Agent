from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

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


def test_candidate_work_queue_claim_progress_and_restart(tmp_path: Path) -> None:
    database = _database(tmp_path)
    client = TestClient(
        create_app(runs_dir=tmp_path / "runs", agent_database=database),
        client=("127.0.0.1", 51234),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-candidate-work"

    queued = client.post(f"{base}/queue")
    replay = client.post(f"{base}/queue")
    assert queued.status_code == replay.status_code == 200
    work = queued.json()["scene_candidate_work"]
    assert work == replay.json()["scene_candidate_work"]
    assert work["status"] == "queued"
    assert [item["domain"] for item in work["definition"]["stage_request"]["operations"]] == [
        "pcg",
        "lighting",
    ]
    assert len(AgentEventStore(database).events(RUN_ID)) == 4

    claim = {
        "schema_id": "artflow-scene-candidate-claim/1",
        "work_sha256": work["definition"]["work_sha256"],
        "session_sha256": work["definition"]["session_sha256"],
        "worker_id": "ue-editor-m19",
    }
    claimed = client.post(f"{base}/claim", json=claim)
    claimed_again = client.post(f"{base}/claim", json=claim)
    assert claimed.status_code == claimed_again.status_code == 200
    assert claimed.json()["scene_candidate_work"]["status"] == "claimed"

    def progress(status: str, action: str, **extra: str):
        return client.post(
            f"{base}/progress",
            json={
                "schema_id": "artflow-scene-candidate-progress/1",
                "work_sha256": work["definition"]["work_sha256"],
                "worker_id": "ue-editor-m19",
                "status": status,
                "action_id": action,
                **extra,
            },
        )

    assert progress("executing", "m19-executing").status_code == 200
    assert progress("reconciling", "m19-reconciling").status_code == 200
    succeeded = progress(
        "succeeded",
        "m19-succeeded",
        outcome_sha256="a" * 64,
        message="候选关卡已完成并复检",
    )
    assert succeeded.status_code == 200
    assert succeeded.json()["scene_candidate_work"]["status"] == "succeeded"

    restored = AgentEventStore(database).load(RUN_ID).scene_candidate_work
    assert restored is not None
    assert restored.status == "succeeded"
    assert restored.outcome_sha256 == "a" * 64
    assert len(AgentEventStore(database).events(RUN_ID)) == 8


def test_candidate_work_rejects_second_worker_paths_and_illegal_progress(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    client = TestClient(
        create_app(runs_dir=tmp_path / "runs", agent_database=database),
        client=("127.0.0.1", 51234),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-candidate-work"
    work = client.post(f"{base}/queue").json()["scene_candidate_work"]
    definition = work["definition"]
    claim = {
        "schema_id": "artflow-scene-candidate-claim/1",
        "work_sha256": definition["work_sha256"],
        "session_sha256": definition["session_sha256"],
        "worker_id": "ue-editor-owner",
    }
    assert client.post(f"{base}/claim", json=claim).status_code == 200
    assert client.post(
        f"{base}/claim", json={**claim, "worker_id": "ue-editor-other"}
    ).status_code == 409
    assert client.post(
        f"{base}/progress",
        json={
            "schema_id": "artflow-scene-candidate-progress/1",
            "work_sha256": definition["work_sha256"],
            "worker_id": "ue-editor-owner",
            "status": "succeeded",
            "action_id": "m19-skip-execution",
            "outcome_sha256": "b" * 64,
        },
    ).status_code == 409
    assert client.post(f"{base}/claim", json={**claim, "receipt_path": "D:/tmp/x.json"}).status_code == 422

    remote = TestClient(
        create_app(
            runs_dir=tmp_path / "remote",
            agent_database=_database(tmp_path / "remote-db"),
        ),
        client=("203.0.113.10", 51234),
    )
    remote_work = remote.post(f"{base}/queue").json()["scene_candidate_work"]
    assert remote.post(
        f"{base}/claim",
        json={
            **claim,
            "work_sha256": remote_work["definition"]["work_sha256"],
            "session_sha256": remote_work["definition"]["session_sha256"],
        },
    ).status_code == 403
