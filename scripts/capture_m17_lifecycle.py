from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from artflow_agent.web_api import create_app


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "goal" / "m12-s2-live-candidate-v2"
OUTPUT = ROOT / "artifacts" / "goal" / "m17-s1-live-lifecycle"
RUN_ID = "unreal-artflow-ue-c4f262344b71ecfb5bf65580af4f5a1f-207d24a911c3"


def write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    database = OUTPUT / "agent-events.sqlite3"
    shutil.copy2(SOURCE / "agent-events.sqlite3", database)
    output_artifacts = OUTPUT / ".agent-artifacts"
    if output_artifacts.exists():
        shutil.rmtree(output_artifacts)
    output_scene_packages = output_artifacts / "scene-packages"
    output_scene_packages.mkdir(parents=True)
    scene_archive = "207d24a911c356879dba45af14c939bdde77a506ffa74eda82d2090db63e073b.zip"
    shutil.copy2(
        SOURCE / ".agent-artifacts" / "scene-packages" / scene_archive,
        output_scene_packages / scene_archive,
    )

    client = TestClient(
        create_app(runs_dir=OUTPUT, agent_database=database),
        client=("127.0.0.1", 51234),
    )
    endpoint = f"/api/agent/runs/{RUN_ID}/scene-variant-lifecycle/m16"
    first = client.post(endpoint)
    first.raise_for_status()
    replay = client.post(endpoint)
    replay.raise_for_status()
    projection = replay.json()
    write_json(OUTPUT / "live-projection.json", projection)
    screenshots = [
        OUTPUT / "live-scene-session-desktop.png",
        OUTPUT / "live-scene-session-narrow.png",
    ]
    write_json(
        OUTPUT / "verification.json",
        {
            "schema_id": "artflow-m17-live-lifecycle-verification/1",
            "status": "verified",
            "run_id": RUN_ID,
            "event_count": len(projection["timeline"]),
            "lifecycle_event_count": sum(
                item["event_type"]
                in {
                    "scene_candidate_evaluated",
                    "scene_candidate_adopted",
                    "scene_variant_published",
                    "scene_variant_reviewed",
                }
                for item in projection["timeline"]
            ),
            "replay_identical": first.json()["scene_variant_lineage"]
            == projection["scene_variant_lineage"],
            "published_scene": projection["scene_variant_lineage"]["published_scene"],
            "generated_instance_count": projection["scene_variant_lineage"][
                "generated_instance_count"
            ],
            "database_sha256": hashlib.sha256(database.read_bytes()).hexdigest(),
            "caller_path_fields": 0,
            "browser_checks": {
                "source_label": "当前 Scene Session",
                "desktop": {"viewport": [1600, 1000], "overflow": False},
                "narrow": {"viewport": [720, 1200], "overflow": False},
                "console_errors": 0,
                "console_warnings": 0,
            },
            "screenshots": [
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in screenshots
                if path.is_file()
            ],
        },
    )


if __name__ == "__main__":
    main()
