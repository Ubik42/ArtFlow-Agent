from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.web_api import create_app

RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"


def test_blender_dcc_work_uses_selected_route_and_existing_lifecycle(
    tmp_path: Path,
) -> None:
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
        "comfy.material.banner_pattern.v1",
        "blender.cloth.banner_authoring.v1",
        "unreal.asset.static_cloth_banner.v1",
    ]
    decision = work["definition"]["route_decision"]
    assert decision["selected_route_id"] == "cloth_banner"
    assert [candidate["route_id"] for candidate in decision["candidates"]] == [
        "cloth_banner",
        "damage_variant",
        "mechanism_shot",
    ]
    assert decision["candidates"][0]["matched_terms"] == ["材质"]
    assert work["definition"]["modeling_request_sha256"] is None
    assert work["definition"]["damage_variant_request_sha256"] is None
    assert work["definition"]["mechanism_shot_request_sha256"] is None
    assert work["definition"]["cloth_banner_request_sha256"] == (
        "4db41b8ff0c213f925a077d36d43294c6cdd129e9f46ddd094c0f50aa5196cf2"
    )
    assert work["definition"]["candidate_scene_path"].endswith("ClothBanner_B_4db41b8ff0c2")

    assert client.post(f"{base}/start").status_code == 202
    finished = None
    for _ in range(100):
        finished = client.get(f"/api/agent/runs/{RUN_ID}")
        if finished.json()["scene_dcc_work"]["status"] == "succeeded":
            break
        time.sleep(0.01)
    assert finished is not None
    assert finished.json()["scene_dcc_work"]["status"] == "succeeded", finished.json()[
        "scene_dcc_work"
    ]["message"]
    restored = AgentEventStore(database).load(RUN_ID).scene_dcc_work
    assert restored is not None
    assert (
        restored.definition.route_decision.model_dump(mode="json")
        == work["definition"]["route_decision"]
    )
    assert restored.outcome_sha256 == work["definition"]["unreal_return_receipt_sha256"]
