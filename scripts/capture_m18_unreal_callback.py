from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from artflow_agent.agent_projection import project_agent_run
from artflow_agent.agent_runtime import AgentEventStore


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "goal" / "m12-s2-live-candidate-v2"
OUTPUT = ROOT / "artifacts" / "goal" / "m18-s1-unreal-callback"
HOST_RECEIPT_ROOT = (
    ROOT
    / "integrations"
    / "unreal"
    / "ArtFlowBridgeHost"
    / "Saved"
    / "ArtFlowSceneBridge"
    / "SceneSessions"
)
RUN_ID = "unreal-artflow-ue-c4f262344b71ecfb5bf65580af4f5a1f-207d24a911c3"
SESSION_SHA256 = "78490746724848bde42be8ce2fbd2eed9ffe5d45a18cfdd81794681d40b0bf19"
TRANSITIONS = ("evaluation", "adoption", "publication", "review")


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def prepare() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    OUTPUT.mkdir(parents=True)
    shutil.copy2(SOURCE / "agent-events.sqlite3", OUTPUT / "agent-events.sqlite3")
    archive = "207d24a911c356879dba45af14c939bdde77a506ffa74eda82d2090db63e073b.zip"
    package_root = OUTPUT / ".agent-artifacts" / "scene-packages"
    package_root.mkdir(parents=True)
    shutil.copy2(
        SOURCE / ".agent-artifacts" / "scene-packages" / archive,
        package_root / archive,
    )
    for path in HOST_RECEIPT_ROOT.glob("lifecycle-m18-*.json"):
        path.unlink()


def verify() -> None:
    store = AgentEventStore(OUTPUT / "agent-events.sqlite3")
    projection = project_agent_run(store, RUN_ID).model_dump(mode="json")
    event_types = [item["event_type"] for item in projection["timeline"]]
    expected = [
        "run_created",
        "scene_attached",
        "scene_session_started",
        "scene_candidate_evaluated",
        "scene_candidate_adopted",
        "scene_variant_published",
        "scene_variant_reviewed",
    ]
    if event_types != expected:
        raise SystemExit(f"unexpected lifecycle event order: {event_types}")

    receipt_output = OUTPUT / "host-receipts"
    receipt_output.mkdir(exist_ok=True)
    receipts: list[dict[str, object]] = []
    for transition in TRANSITIONS:
        source = HOST_RECEIPT_ROOT / f"lifecycle-m18-{transition}.json"
        value = json.loads(source.read_text(encoding="utf-8-sig"))
        if (
            value.get("schema") != "artflow-unreal-lifecycle-callback-receipt/1"
            or value.get("success") is not True
            or value.get("run_id") != RUN_ID
            or value.get("session_sha256") != SESSION_SHA256
            or value.get("transition") != transition
        ):
            raise SystemExit(f"invalid Unreal callback receipt: {source}")
        target = receipt_output / source.name
        shutil.copy2(source, target)
        receipts.append(
            {
                "transition": transition,
                "artifact_sha256": value["artifact_sha256"],
                "event_type": value["event_type"],
                "receipt": target.relative_to(ROOT).as_posix(),
                "receipt_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    write_json(OUTPUT / "live-projection.json", projection)
    write_json(
        OUTPUT / "verification.json",
        {
            "schema_id": "artflow-m18-unreal-callback-verification/1",
            "status": "verified",
            "engine_version": "5.8.1",
            "run_id": RUN_ID,
            "session_sha256": SESSION_SHA256,
            "event_count": len(event_types),
            "lifecycle_event_count": len(TRANSITIONS),
            "event_order": event_types,
            "host_receipts": receipts,
            "published_scene": projection["scene_variant_lineage"]["published_scene"],
            "caller_path_fields": 0,
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
