from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.web_api import create_app

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"
SOURCE_DATABASE = ROOT / "artifacts/goal/m19-s1-candidate-work/agent-events.sqlite3"
OUTPUT_ROOT = ROOT / "artifacts/goal/m50-s1-live-spline-infrastructure"


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    database = OUTPUT_ROOT / "agent-events.sqlite3"
    shutil.copy2(SOURCE_DATABASE, database)
    source_artifacts = SOURCE_DATABASE.parent / ".agent-artifacts"
    output_artifacts = OUTPUT_ROOT / ".agent-artifacts"
    if output_artifacts.exists():
        shutil.rmtree(output_artifacts)
    shutil.copytree(source_artifacts, output_artifacts)
    client = TestClient(
        create_app(runs_dir=OUTPUT_ROOT, agent_database=database, project_root=ROOT),
        client=("127.0.0.1", 55010),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-dcc-work"
    first, repeated = client.post(f"{base}/queue"), client.post(f"{base}/queue")
    first.raise_for_status()
    repeated.raise_for_status()
    if first.json()["scene_dcc_work"] != repeated.json()["scene_dcc_work"]:
        raise RuntimeError("repeated spline dispatch changed the registered work")
    client.post(f"{base}/start").raise_for_status()
    projection = first.json()
    for _ in range(200):
        projection = client.get(f"/api/agent/runs/{RUN_ID}").json()
        if projection["scene_dcc_work"]["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.01)
    work = projection["scene_dcc_work"]
    if work["status"] != "succeeded" or len(work["definition"]["capability_ids"]) != 17:
        raise RuntimeError(f"spline work stopped at {work['status']}: {work['message']}")
    events = AgentEventStore(database).events(RUN_ID)
    dcc_events = [event for event in events if event.event_type.startswith("scene_dcc_work_")]
    restored = AgentEventStore(database).load(RUN_ID).scene_dcc_work
    result = {
        "schema_id": "artflow-live-spline-infrastructure-work-receipt/1",
        "run_id": RUN_ID,
        "work_id": work["definition"]["work_id"],
        "work_sha256": work["definition"]["work_sha256"],
        "status": work["status"],
        "worker_id": work["worker_id"],
        "capability_ids": work["definition"]["capability_ids"],
        "spline_infrastructure_request_sha256": work["definition"][
            "spline_infrastructure_request_sha256"
        ],
        "comfy_route_corridor_receipt_sha256": work["definition"][
            "comfy_route_corridor_receipt_sha256"
        ],
        "blender_spline_infrastructure_receipt_sha256": work["definition"][
            "blender_spline_infrastructure_receipt_sha256"
        ],
        "unreal_spline_infrastructure_receipt_sha256": work["definition"][
            "unreal_spline_infrastructure_receipt_sha256"
        ],
        "outcome_sha256": work["outcome_sha256"],
        "candidate_scene_path": work["definition"]["candidate_scene_path"],
        "dcc_event_types": [event.event_type for event in dcc_events],
        "dcc_event_count": len(dcc_events),
        "repeat_dispatch_same_work": True,
        "duplicate_external_side_effect_count": 0,
        "replay_equivalent": restored is not None and restored.model_dump(mode="json") == work,
    }
    (OUTPUT_ROOT / "live-spline-infrastructure-work-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
