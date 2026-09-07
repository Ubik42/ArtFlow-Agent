from __future__ import annotations

import shutil
import time
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
        "blender.shot.rain_breakthrough.v1",
        "blender.lookdev.scene_target.v1",
    ]
    assert work["definition"]["accepted_visual_target_sha256"] == (
        "0f65a7a7bb0f1bdd0bdf9ab41e2b9e3367d0c6a15be364a5b3b9e8ccc9ff41cb"
    )
    assert work["definition"]["candidate_scene_path"].endswith("Lookdev_B_4a01b62f9d58")

    assert client.post(f"{base}/start").status_code == 202
    finished = None
    for _ in range(100):
        finished = client.get(f"/api/agent/runs/{RUN_ID}")
        if finished.json()["scene_dcc_work"]["status"] == "succeeded":
            break
        time.sleep(0.01)
    assert finished is not None
    assert finished.json()["scene_dcc_work"]["status"] == "succeeded"
    restored = AgentEventStore(database).load(RUN_ID).scene_dcc_work
    assert restored is not None
    assert restored.outcome_sha256 == work["definition"]["unreal_return_receipt_sha256"]
