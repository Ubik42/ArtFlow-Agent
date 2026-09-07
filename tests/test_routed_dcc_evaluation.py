from __future__ import annotations

import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.routed_dcc_evaluation import seal_routed_dcc_visual_observation
from artflow_agent.web_api import create_app

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"


def test_selected_dcc_candidate_is_evaluated_adopted_and_publishable(
    tmp_path: Path,
) -> None:
    source = ROOT / "artifacts/goal/m19-s1-candidate-work"
    database = tmp_path / "agent-events.sqlite3"
    shutil.copy2(source / "agent-events.sqlite3", database)
    shutil.copytree(source / ".agent-artifacts", tmp_path / ".agent-artifacts")
    client = TestClient(
        create_app(runs_dir=tmp_path, agent_database=database, project_root=ROOT),
        client=("127.0.0.1", 56010),
    )
    base = f"/api/agent/runs/{RUN_ID}"
    client.post(f"{base}/scene-dcc-work/queue").raise_for_status()
    client.post(f"{base}/scene-dcc-work/start").raise_for_status()
    projection = client.get(base).json()
    for _ in range(200):
        projection = client.get(base).json()
        if projection["scene_dcc_work"]["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.01)
    definition = projection["scene_dcc_work"]["definition"]
    observation = seal_routed_dcc_visual_observation(
        route_decision_sha256=definition["route_decision"]["decision_sha256"],
        candidate_preview_sha256=definition["cloth_banner_unreal_preview_sha256"],
        claims=[
            {
                "dimension": "material_direction",
                "verdict": "passed",
                "confidence": 0.94,
                "rationale": "纹章、旧化边缘与暖色场景方向一致，材质层次清楚。",
            },
            {
                "dimension": "silhouette_readability",
                "verdict": "passed",
                "confidence": 0.92,
                "rationale": "风场形变形成明确外轮廓，旗面没有不可读的折叠穿插。",
            },
            {
                "dimension": "scene_attachment",
                "verdict": "passed",
                "confidence": 0.91,
                "rationale": "旗帜从登记挂点自然垂落，尺寸与相邻模块关系可信。",
            },
            {
                "dimension": "production_readiness",
                "verdict": "passed",
                "confidence": 0.95,
                "rationale": "当前结果具备材质、碰撞与稳定定格网格，可进入版本候选。",
            },
        ],
    )
    evaluated = client.post(
        f"{base}/scene-dcc-work/evaluate",
        json=observation.model_dump(mode="json"),
    )
    assert evaluated.status_code == 200, evaluated.text
    evaluated.raise_for_status()
    first_record = evaluated.json()["scene_dcc_candidate_evaluation"]
    assert first_record["domain_evaluation"]["status"] == "accepted"
    assert len(first_record["technical_checks"]) == 6
    assert all(check["status"] == "passed" for check in first_record["technical_checks"])
    repeated = client.post(
        f"{base}/scene-dcc-work/evaluate",
        json=observation.model_dump(mode="json"),
    )
    repeated.raise_for_status()
    assert repeated.json()["scene_dcc_candidate_evaluation"] == first_record

    adopted = client.post(f"{base}/scene-dcc-work/adopt")
    adopted.raise_for_status()
    decision = adopted.json()["scene_candidate_adoption"]["decision"]
    assert decision["orchestrator"] == "codex"
    assert decision["evaluation_sha256"] == first_record["domain_evaluation"][
        "evaluation_sha256"
    ]
    assert decision["candidate_scene"] == definition["candidate_scene_path"]
    publish_request = client.get(f"{base}/current-variant/publish-request")
    assert publish_request.status_code == 200, publish_request.text
    publish_request.raise_for_status()
    assert publish_request.json()["decision"] == decision

    restored = AgentEventStore(database).load(RUN_ID)
    assert restored.scene_dcc_candidate_evaluation == AgentEventStore(database).load(
        RUN_ID
    ).scene_dcc_candidate_evaluation
    assert restored.scene_candidate_adoption is not None
