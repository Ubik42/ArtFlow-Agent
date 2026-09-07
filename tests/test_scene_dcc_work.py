from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.web_api import create_app

RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"


def test_blender_dcc_work_uses_current_session_event_lifecycle(tmp_path: Path) -> None:
    root = Path(__file__).parents[1]
    source = root / "artifacts/goal/m19-s1-candidate-work/agent-events.sqlite3"
    database = tmp_path / "agent-events.sqlite3"
    shutil.copy2(source, database)
    client = TestClient(
        create_app(
            runs_dir=tmp_path / "runs",
            agent_database=database,
            project_root=root,
        ),
        client=("127.0.0.1", 51234),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-dcc-work"

    queued = client.post(f"{base}/queue")
    replayed = client.post(f"{base}/queue")
    assert queued.status_code == replayed.status_code == 200
    work = queued.json()["scene_dcc_work"]
    assert work == replayed.json()["scene_dcc_work"]
    assert work["definition"]["capability_ids"] == [
        "blender.architectural_prop.weathered_shrine.v1",
        "blender.comfy_pbr.assembly.v1",
        "blender.geometry_nodes.shrine_courtyard.v1",
    ]

    claim = {
        "schema_id": "artflow-scene-dcc-claim/1",
        "work_sha256": work["definition"]["work_sha256"],
        "session_sha256": work["definition"]["session_sha256"],
        "worker_id": "blender-worker-m23",
    }
    assert client.post(f"{base}/claim", json=claim).status_code == 200

    def progress(status: str, action: str, outcome: str | None = None):
        payload = {
            "schema_id": "artflow-scene-dcc-progress/1",
            "work_sha256": work["definition"]["work_sha256"],
            "worker_id": "blender-worker-m23",
            "status": status,
            "action_id": action,
        }
        if outcome:
            payload["outcome_sha256"] = outcome
        return client.post(f"{base}/progress", json=payload)

    assert progress("executing", "m23-dcc-executing").status_code == 200
    assert progress("reconciling", "m23-dcc-reconciling").status_code == 200
    finished = progress("succeeded", "m23-dcc-succeeded", "6" * 64)
    assert finished.status_code == 200
    assert finished.json()["scene_dcc_work"]["status"] == "succeeded"
    restored = AgentEventStore(database).load(RUN_ID).scene_dcc_work
    assert restored is not None and restored.outcome_sha256 == "6" * 64
