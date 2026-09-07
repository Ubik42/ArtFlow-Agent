from __future__ import annotations

import json
import shutil
from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.scene_dcc_work import (
    SceneDccWorkProgressRequest,
    compile_current_blender_dcc_work,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"
SOURCE_DATABASE = ROOT / "artifacts/goal/m19-s1-candidate-work/agent-events.sqlite3"
OUTPUT_ROOT = ROOT / "artifacts/goal/m23-s3-session-dcc-work"


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    database = OUTPUT_ROOT / "agent-events.sqlite3"
    shutil.copy2(SOURCE_DATABASE, database)
    store = AgentEventStore(database)
    state = store.load(RUN_ID)
    session = state.scene_sessions[-1]
    definition = compile_current_blender_dcc_work(
        ROOT,
        run_id=RUN_ID,
        session_id=session.session_id,
        session_sha256=session.session_sha256,
    )
    store.queue_scene_dcc_work(RUN_ID, definition)
    store.claim_scene_dcc_work(
        RUN_ID,
        work_sha256=definition.work_sha256,
        worker_id="blender-worker-m23",
    )
    for status in ("executing", "reconciling"):
        store.progress_scene_dcc_work(
            RUN_ID,
            SceneDccWorkProgressRequest(
                work_sha256=definition.work_sha256,
                worker_id="blender-worker-m23",
                status=status,
                action_id=f"m23-dcc-{status}",
                message="使用已验证内容身份继续 DCC 链路" if status == "executing" else "对账 Unreal 回流回执",
            ),
        )
    store.progress_scene_dcc_work(
        RUN_ID,
        SceneDccWorkProgressRequest(
            work_sha256=definition.work_sha256,
            worker_id="blender-worker-m23",
            status="succeeded",
            action_id="m23-dcc-succeeded",
            outcome_sha256=definition.unreal_return_receipt_sha256,
            message="ComfyUI PBR、Blender 编辑源与 Unreal 候选已完成对账",
        ),
    )
    restored = AgentEventStore(database).load(RUN_ID).scene_dcc_work
    if restored is None or restored.status != "succeeded":
        raise RuntimeError("DCC work did not survive event replay")
    result = {
        "schema_id": "artflow-session-dcc-work-receipt/1",
        "run_id": RUN_ID,
        "session_id": session.session_id,
        "definition": definition.model_dump(mode="json"),
        "final_state": restored.model_dump(mode="json"),
        "event_count": len(store.events(RUN_ID)),
        "replayed": True,
        "external_generation_repeated": False,
    }
    (OUTPUT_ROOT / "session-dcc-work-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
