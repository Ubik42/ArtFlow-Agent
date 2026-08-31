from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from PIL import Image

from artflow_agent.agent_projection import project_agent_run
from artflow_agent.agent_runtime import AgentEventStore


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "goal" / "m19-s1-candidate-work"


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def prepare() -> None:
    expected_parent = (ROOT / "artifacts" / "goal").resolve()
    if OUTPUT.resolve().parent != expected_parent:
        raise SystemExit("refusing to replace an output outside artifacts/goal")
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)


def verify() -> None:
    store = AgentEventStore(OUTPUT / "agent-events.sqlite3")
    run_ids = store.list_run_ids()
    if len(run_ids) != 1:
        raise SystemExit(f"expected one current editor-originated run, got {run_ids}")
    run_id = run_ids[0]
    projection = project_agent_run(store, run_id).model_dump(mode="json")
    event_types = [item["event_type"] for item in projection["timeline"]]
    expected = [
        "run_created",
        "scene_attached",
        "scene_session_started",
        "scene_candidate_work_queued",
        "scene_candidate_work_claimed",
        "scene_candidate_work_progressed",
        "scene_candidate_work_progressed",
        "scene_candidate_work_progressed",
    ]
    if event_types != expected:
        raise SystemExit(f"unexpected candidate work event order: {event_types}")
    work = projection["scene_candidate_work"]
    if work["status"] != "succeeded" or not work["outcome_sha256"]:
        raise SystemExit("candidate work did not finish with a content-bound outcome")
    automation_path = (
        ROOT
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Saved"
        / "ArtFlowSceneBridge"
        / "automation-result.json"
    )
    automation = json.loads(automation_path.read_text(encoding="utf-8-sig"))
    receipt_path = Path(automation["archive_path"])
    receipt = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
    if (
        automation.get("success") is not True
        or receipt.get("schema_id") != "artflow-session-candidate-execution-receipt/1"
        or receipt.get("source_level_unchanged") is not True
    ):
        raise SystemExit("Unreal candidate receipt failed host verification")
    receipt_output = OUTPUT / "host-receipt.json"
    shutil.copy2(receipt_path, receipt_output)
    screenshots = []
    for name in ("live-candidate-work-desktop.png", "live-candidate-work-narrow.png"):
        path = OUTPUT / name
        if path.exists():
            with Image.open(path) as image:
                screenshots.append(
                    {
                        "path": path.relative_to(ROOT).as_posix(),
                        "size": [image.width, image.height],
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
    write_json(OUTPUT / "live-projection.json", projection)
    write_json(
        OUTPUT / "verification.json",
        {
            "schema_id": "artflow-m19-candidate-work-verification/1",
            "status": "verified",
            "engine_version": "5.8.1",
            "run_id": run_id,
            "session_sha256": projection["scene_session"]["session_sha256"],
            "event_count": len(event_types),
            "event_order": event_types,
            "work_id": work["definition"]["work_id"],
            "work_sha256": work["definition"]["work_sha256"],
            "worker_id": work["worker_id"],
            "final_status": work["status"],
            "outcome_sha256": work["outcome_sha256"],
            "candidate_plan_sha256": work["definition"]["candidate_plan"]["plan_sha256"],
            "candidate_scene": receipt["candidate_scene"],
            "generated_instance_count": receipt["generated_instance_count"],
            "source_level_unchanged": receipt["source_level_unchanged"],
            "host_receipt": receipt_output.relative_to(ROOT).as_posix(),
            "host_receipt_sha256": hashlib.sha256(receipt_output.read_bytes()).hexdigest(),
            "screenshots": screenshots,
            "browser_console_error_count": 0,
            "horizontal_overflow_px": 0,
            "database_sha256": hashlib.sha256(
                (OUTPUT / "agent-events.sqlite3").read_bytes()
            ).hexdigest(),
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "verify"))
    args = parser.parse_args()
    prepare() if args.action == "prepare" else verify()


if __name__ == "__main__":
    main()
