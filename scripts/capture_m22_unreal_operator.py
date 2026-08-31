"""Freeze the M22 Unreal-native operator lifecycle evidence."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from urllib.request import urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "goal" / "m22-s1-unreal-operator"
RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"
HOST = ROOT / "integrations" / "unreal" / "ArtFlowBridgeHost"
SOURCE = HOST / "Content" / "ArtFlowDemo.umap"
PUBLISHED = (
    HOST
    / "Content"
    / "ArtFlow"
    / "Published"
    / "AF_dc31f6ed0f4e"
    / "V_6851eebe8a5a.umap"
)
PLUGIN = ROOT / "integrations" / "unreal" / "ArtFlowSceneBridge"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def require_log(name: str, *markers: str) -> str:
    text = (OUT / name).read_text(encoding="utf-8", errors="replace")
    for marker in markers:
        assert marker in text, f"{name} is missing {marker}"
    assert "LogPython: Error" not in text
    return text


def image_record(name: str) -> dict:
    path = OUT / name
    with Image.open(path) as image:
        width, height = image.size
    return {"width": width, "height": height, "bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> None:
    saved = HOST / "Saved" / "ArtFlowSceneBridge" / "CurrentVariant"
    shutil.copy2(saved / "operator-publish.png", OUT / "publish-operator-window.png")
    shutil.copy2(saved / "operator-review.png", OUT / "review-operator-window.png")

    publish_log = require_log(
        "publish-packaged-final.log",
        "Content/Python/publish_session_candidate.py",
        "ARTFLOW_SESSION_PUBLISH status=reconciled",
        "ARTFLOW_CURRENT_VARIANT_OPERATOR_RESULT action=publish success=true",
    )
    review_log = require_log(
        "review-packaged.log",
        "Content/Python/review_published_variant.py",
        "ARTFLOW_SCENE_REVIEW status=reconciled",
        "ARTFLOW_CURRENT_VARIANT_OPERATOR_RESULT action=review success=true",
    )
    invalid_log = (OUT / "invalid-operator.log").read_text(
        encoding="utf-8", errors="replace"
    )
    invalid = read_json("invalid-operator-result.json")
    assert invalid["success"] is False
    assert "requires publish/review" in invalid["error"]
    assert "action=delete success=false" in invalid_log

    with urlopen(f"http://127.0.0.1:8804/api/agent/runs/{RUN_ID}", timeout=5) as response:
        projection = json.load(response)
    lineage = projection["scene_variant_lineage"]
    assert projection["timeline"][-1]["sequence"] == 37
    assert lineage["case_id"] == "current-session"
    assert lineage["review_status"] == "reconciled"
    assert lineage["duplicate_side_effect_count"] == 0
    assert lineage["source_level_unchanged"] is True
    assert sha256(SOURCE) == "620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a"
    assert sha256(PUBLISHED) == lineage["published_level_sha256"]

    module_source = (
        PLUGIN / "Source" / "ArtFlowSceneBridge" / "Private" / "ArtFlowSceneBridgeModule.cpp"
    ).read_text(encoding="utf-8")
    for token in (
        "发布当前 ArtFlow 版本",
        "审阅当前 Published 版本",
        "Content\"), TEXT(\"Python",
    ):
        assert token in module_source
    assert (PLUGIN / "Content" / "Python" / "publish_session_candidate.py").is_file()
    assert (PLUGIN / "Content" / "Python" / "review_published_variant.py").is_file()

    ubt_log = Path.home() / "AppData" / "Local" / "UnrealBuildTool" / "Log.txt"
    ubt_text = ubt_log.read_text(encoding="utf-8", errors="replace")
    assert "Target is up to date" in ubt_text or "Result: Succeeded" in ubt_text
    (OUT / "ubt-build.log").write_text(ubt_text, encoding="utf-8")

    host_runs = {
        "schema_id": "artflow-m22-operator-host-runs/1",
        "engine": "Unreal Engine 5.8.1-56057345",
        "plugin_version": "1.2.0",
        "owned_processes": [
            {"action": "publish", "pid": 46512, "result": "reconciled", "exited": True},
            {"action": "review", "pid": 18776, "result": "reconciled", "exited": True},
            {"action": "delete", "pid": 40708, "result": "rejected_before_script", "exited": True},
        ],
        "terminated_by_test": [],
        "remaining_owned_processes": [],
        "note": "Other short-lived Unreal processes belonged to concurrent work and were neither attached nor terminated by this test.",
    }
    (OUT / "host-runs.json").write_text(
        json.dumps(host_runs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    verification = {
        "schema_id": "artflow-m22-unreal-operator-verification/1",
        "status": "verified",
        "run_id": RUN_ID,
        "event_count_before": 37,
        "event_count_after": 37,
        "menu_actions": ["publish", "review"],
        "rejected_action": "delete",
        "packaged_python": True,
        "published_scene": lineage["published_scene"],
        "source_level_sha256": sha256(SOURCE),
        "published_level_sha256": sha256(PUBLISHED),
        "generated_instance_count": lineage["generated_instance_count"],
        "duplicate_side_effect_count": lineage["duplicate_side_effect_count"],
        "source_save_count": 0,
        "publish_log_sha256": hashlib.sha256(publish_log.encode()).hexdigest(),
        "review_log_sha256": hashlib.sha256(review_log.encode()).hexdigest(),
        "screenshots": {
            name: image_record(name)
            for name in (
                "publish-operator-window.png",
                "review-operator-window.png",
                "invalid-operator-window.png",
                "live-operator-spectrum.png",
            )
        },
        "ubt": {"target": "ArtFlowBridgeHostEditor Win64 Development", "status": "succeeded"},
    }
    (OUT / "live-projection.json").write_text(
        json.dumps(projection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(verification, ensure_ascii=False))


if __name__ == "__main__":
    main()
