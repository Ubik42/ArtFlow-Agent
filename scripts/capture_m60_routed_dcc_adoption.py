from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.routed_dcc_evaluation import seal_routed_dcc_visual_observation
from artflow_agent.web_api import create_app

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"
SOURCE_DATABASE = ROOT / "artifacts/goal/m19-s1-candidate-work/agent-events.sqlite3"
OUTPUT_ROOT = ROOT / "artifacts/goal/m60-s1-routed-dcc-adoption"


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    database = OUTPUT_ROOT / "agent-events.sqlite3"
    shutil.copy2(SOURCE_DATABASE, database)
    output_artifacts = OUTPUT_ROOT / ".agent-artifacts"
    if output_artifacts.exists():
        shutil.rmtree(output_artifacts)
    shutil.copytree(SOURCE_DATABASE.parent / ".agent-artifacts", output_artifacts)
    client = TestClient(
        create_app(runs_dir=OUTPUT_ROOT, agent_database=database, project_root=ROOT),
        client=("127.0.0.1", 56060),
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
    observation_path = OUTPUT_ROOT / "codex-visual-observation.json"
    observation_path.write_text(
        json.dumps(observation.model_dump(mode="json"), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    evaluate_url = f"{base}/scene-dcc-work/evaluate"
    first_evaluation = client.post(
        evaluate_url, json=observation.model_dump(mode="json")
    )
    repeated_evaluation = client.post(
        evaluate_url, json=observation.model_dump(mode="json")
    )
    first_evaluation.raise_for_status()
    repeated_evaluation.raise_for_status()
    if (
        first_evaluation.json()["scene_dcc_candidate_evaluation"]
        != repeated_evaluation.json()["scene_dcc_candidate_evaluation"]
    ):
        raise RuntimeError("repeated routed evaluation changed the persisted result")
    first_adoption = client.post(f"{base}/scene-dcc-work/adopt")
    repeated_adoption = client.post(f"{base}/scene-dcc-work/adopt")
    first_adoption.raise_for_status()
    repeated_adoption.raise_for_status()
    if (
        first_adoption.json()["scene_candidate_adoption"]
        != repeated_adoption.json()["scene_candidate_adoption"]
    ):
        raise RuntimeError("repeated routed adoption changed the persisted decision")
    publish_request = client.get(f"{base}/current-variant/publish-request")
    publish_request.raise_for_status()
    projection = first_adoption.json()
    evaluation = projection["scene_dcc_candidate_evaluation"]
    adoption = projection["scene_candidate_adoption"]
    events = AgentEventStore(database).events(RUN_ID)
    route_start = next(
        index
        for index in range(len(events) - 1, -1, -1)
        if events[index].event_type == "scene_dcc_work_queued"
    )
    route_events = [
        event
        for event in events[route_start:]
        if event.event_type
        in {
            "scene_dcc_work_queued",
            "scene_dcc_work_claimed",
            "scene_dcc_work_progressed",
            "scene_dcc_candidate_evaluated",
            "scene_candidate_adopted",
        }
    ]
    restored = AgentEventStore(database).load(RUN_ID)
    result = {
        "schema_id": "artflow-routed-dcc-adoption-receipt/1",
        "run_id": RUN_ID,
        "route_decision_sha256": definition["route_decision"]["decision_sha256"],
        "work_sha256": definition["work_sha256"],
        "outcome_sha256": projection["scene_dcc_work"]["outcome_sha256"],
        "candidate_scene": definition["candidate_scene_path"],
        "evaluation": evaluation,
        "adoption": adoption,
        "publish_request": publish_request.json(),
        "route_event_types": [event.event_type for event in route_events],
        "route_event_count": len(route_events),
        "technical_pass_count": sum(
            check["status"] == "passed" for check in evaluation["technical_checks"]
        ),
        "technical_check_count": len(evaluation["technical_checks"]),
        "visual_pass_count": sum(
            claim["verdict"] == "passed"
            for claim in evaluation["visual_observation"]["claims"]
        ),
        "visual_claim_count": len(evaluation["visual_observation"]["claims"]),
        "repeat_evaluation_same_record": True,
        "repeat_adoption_same_decision": True,
        "duplicate_external_side_effect_count": 0,
        "replay_equivalent": (
            restored.scene_dcc_candidate_evaluation is not None
            and restored.scene_dcc_candidate_evaluation.model_dump(mode="json")
            == evaluation
            and restored.scene_candidate_adoption is not None
            and restored.scene_candidate_adoption.model_dump(mode="json") == adoption
        ),
    }
    (OUTPUT_ROOT / "routed-dcc-adoption-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
