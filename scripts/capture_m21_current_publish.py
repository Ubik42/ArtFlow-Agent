"""Freeze the current-session publish/review proof without rerunning Unreal."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "goal" / "m21-s1-current-publish"
RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"
SOURCE = ROOT / "integrations" / "unreal" / "ArtFlowBridgeHost" / "Content" / "ArtFlowDemo.umap"
PUBLISHED = (
    ROOT / "integrations" / "unreal" / "ArtFlowBridgeHost" / "Content" / "ArtFlow"
    / "Published" / "AF_dc31f6ed0f4e" / "V_6851eebe8a5a.umap"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def main() -> None:
    with urlopen(f"http://127.0.0.1:8804/api/agent/runs/{RUN_ID}", timeout=5) as response:
        projection = json.load(response)

    publish_created = read_json("publish-created-receipt.json")
    publish_reconciled = read_json("publish-reconciled-receipt.json")
    review_inspected = read_json("review-inspected-receipt.json")
    review_reconciled = read_json("review-reconciled-receipt.json")
    lineage = projection["scene_variant_lineage"]

    assert projection["timeline"][-1]["sequence"] == 37
    assert [publish_created["status"], publish_reconciled["status"]] == ["published", "reconciled"]
    assert [review_inspected["status"], review_reconciled["status"]] == ["inspected", "reconciled"]
    assert lineage["case_id"] == "current-session" and lineage["review_status"] == "reconciled"
    assert lineage["duplicate_side_effect_count"] == 0 and lineage["source_level_unchanged"] is True
    assert publish_created["request_sha256"] == publish_reconciled["request_sha256"]
    assert review_inspected["review_sha256"] == review_reconciled["review_sha256"]
    assert sha256(PUBLISHED) == lineage["published_level_sha256"]
    assert sha256(SOURCE) == publish_reconciled["source_level_sha256_after"]
    assert publish_reconciled["generated_instance_count"] == 12
    assert review_reconciled["source_save_count"] == 0

    screenshots = {}
    for name in (
        "live-published-review-desktop.png",
        "live-published-review-narrow.png",
    ):
        path = OUT / name
        screenshots[name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}

    verification = {
        "schema_id": "artflow-m21-current-publish-verification/1",
        "status": "verified",
        "run_id": RUN_ID,
        "event_count": 37,
        "published_scene": lineage["published_scene"],
        "published_level_sha256": lineage["published_level_sha256"],
        "source_level_sha256": sha256(SOURCE),
        "source_level_unchanged": True,
        "protected_state_sha256": publish_reconciled["protected_state_sha256"],
        "generated_instance_count": 12,
        "duplicate_package_count": 0,
        "source_save_count": 0,
        "publish_statuses": ["published", "reconciled"],
        "review_statuses": ["inspected", "reconciled"],
        "lineage_case": "current-session",
        "screenshots": screenshots,
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
