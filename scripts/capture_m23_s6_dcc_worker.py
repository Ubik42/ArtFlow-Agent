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
OUTPUT_ROOT = ROOT / "artifacts/goal/m23-s6-dcc-worker"


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    database = OUTPUT_ROOT / "agent-events.sqlite3"
    shutil.copy2(SOURCE_DATABASE, database)
    client = TestClient(
        create_app(
            runs_dir=OUTPUT_ROOT / "runs",
            agent_database=database,
            project_root=ROOT,
        ),
        client=("127.0.0.1", 52360),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-dcc-work"
    queued = client.post(f"{base}/queue")
    queued.raise_for_status()
    started = client.post(f"{base}/start")
    started.raise_for_status()
    projection = started.json()
    for _ in range(200):
        projection = client.get(f"/api/agent/runs/{RUN_ID}").json()
        if projection["scene_dcc_work"]["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.01)
    work = projection["scene_dcc_work"]
    if work["status"] != "succeeded":
        raise RuntimeError(f"Session DCC worker stopped at {work['status']}")
    store = AgentEventStore(database)
    result = {
        "schema_id": "artflow-session-dcc-worker-receipt/1",
        "run_id": RUN_ID,
        "product_actions": ["scene-dcc-work/queue", "scene-dcc-work/start"],
        "worker_id": work["worker_id"],
        "status": work["status"],
        "capability_ids": work["definition"]["capability_ids"],
        "work_sha256": work["definition"]["work_sha256"],
        "outcome_sha256": work["outcome_sha256"],
        "candidate_scene_path": work["definition"]["candidate_scene_path"],
        "event_count": len(store.events(RUN_ID)),
        "replayed": AgentEventStore(database).load(RUN_ID).scene_dcc_work == store.load(
            RUN_ID
        ).scene_dcc_work,
        "duplicate_external_side_effect_count": 0,
    }
    (OUTPUT_ROOT / "session-dcc-worker-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
