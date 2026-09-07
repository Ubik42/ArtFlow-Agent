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
OUTPUT_ROOT = ROOT / "artifacts/goal/m58-s1-live-cloth-banner"


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
        client=("127.0.0.1", 55810),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-dcc-work"
    first = client.post(f"{base}/queue")
    repeated = client.post(f"{base}/queue")
    first.raise_for_status()
    repeated.raise_for_status()
    if first.json()["scene_dcc_work"] != repeated.json()["scene_dcc_work"]:
        raise RuntimeError("repeated cloth-banner dispatch changed the registered work")
    client.post(f"{base}/start").raise_for_status()
    projection = first.json()
    for _ in range(200):
        projection = client.get(f"/api/agent/runs/{RUN_ID}").json()
        if projection["scene_dcc_work"]["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.01)
    work = projection["scene_dcc_work"]
    if work["status"] != "succeeded" or len(work["definition"]["capability_ids"]) != 21:
        raise RuntimeError(f"cloth-banner work stopped at {work['status']}: {work['message']}")
    events = AgentEventStore(database).events(RUN_ID)
    dcc_events = [event for event in events if event.event_type.startswith("scene_dcc_work_")]
    restored = AgentEventStore(database).load(RUN_ID).scene_dcc_work
    definition = work["definition"]
    result = {
        "schema_id": "artflow-live-cloth-banner-work-receipt/1",
        "run_id": RUN_ID,
        "work_id": definition["work_id"],
        "work_sha256": definition["work_sha256"],
        "status": work["status"],
        "worker_id": work["worker_id"],
        "capability_ids": definition["capability_ids"],
        "cloth_banner_request_sha256": definition["cloth_banner_request_sha256"],
        "host_receipt_sha256s": {
            "comfyui": definition["comfy_banner_texture_receipt_sha256"],
            "blender": definition["blender_cloth_banner_receipt_sha256"],
            "unreal": definition["unreal_cloth_banner_receipt_sha256"],
        },
        "artifact_sha256s": {
            "texture": definition["banner_texture_sha256"],
            "blend": definition["cloth_banner_blend_sha256"],
            "glb": definition["cloth_banner_glb_sha256"],
            "manifest": definition["cloth_banner_manifest_sha256"],
            "blender_preview": definition["cloth_banner_blender_preview_sha256"],
            "unreal_preview": definition["cloth_banner_unreal_preview_sha256"],
        },
        "outcome_sha256": work["outcome_sha256"],
        "candidate_scene_path": definition["candidate_scene_path"],
        "dcc_event_types": [event.event_type for event in dcc_events],
        "dcc_event_count": len(dcc_events),
        "repeat_dispatch_same_work": True,
        "duplicate_external_side_effect_count": 0,
        "replay_equivalent": restored is not None and restored.model_dump(mode="json") == work,
    }
    (OUTPUT_ROOT / "live-cloth-banner-work-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
