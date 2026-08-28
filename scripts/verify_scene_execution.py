from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from artflow_agent.contracts import (
    SceneDispositionReceipt,
    SceneDryRunReceipt,
    SceneExecutionReceipt,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an ArtFlow UE candidate lifecycle.")
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--candidate-map", type=Path, required=True)
    parser.add_argument("--published-map", type=Path, required=True)
    parser.add_argument("--dry-run-package", type=Path, required=True)
    args = parser.parse_args()

    root = args.evidence_dir.resolve()
    execution = SceneExecutionReceipt.model_validate_json(
        (root / "scene-execution-receipt.json").read_text(encoding="utf-8")
    )
    reconcile = SceneExecutionReceipt.model_validate_json(
        (root / "scene-execution-reconcile-receipt.json").read_text(encoding="utf-8")
    )
    publish = SceneDispositionReceipt.model_validate_json(
        (root / "scene-publish-receipt.json").read_text(encoding="utf-8")
    )
    discard = SceneDispositionReceipt.model_validate_json(
        (root / "scene-discard-receipt.json").read_text(encoding="utf-8")
    )
    lifecycle = json.loads((root / "host-lifecycle.json").read_text(encoding="utf-8"))
    beauty = root / "candidate-beauty.png"
    with zipfile.ZipFile(args.dry_run_package) as archive:
        plan_bytes = archive.read("scene-change-plan.json")
        twin_bytes = archive.read("scene-digital-twin.json")
        dry_run = SceneDryRunReceipt.model_validate_json(
            archive.read("scene-dry-run-receipt.json")
        )

    assert execution.reconciled is False
    assert execution.plan_id == dry_run.plan_id
    assert execution.twin_id == dry_run.twin_id
    assert execution.plan_sha256 == hashlib.sha256(plan_bytes).hexdigest()
    assert execution.twin_sha256 == hashlib.sha256(twin_bytes).hexdigest()
    assert reconcile.reconciled is True
    assert all(item.status == "reconciled" for item in reconcile.operations)
    assert execution.operations[1].generated_instance_count == 12
    assert reconcile.operations[1].generated_instance_count == 12
    assert publish.disposition == "published" and publish.source_overwritten is False
    assert discard.disposition == "discarded" and discard.source_overwritten is False
    assert sha256(beauty) == execution.candidate_beauty_sha256
    assert sha256(args.source_map) == execution.source_scene_fingerprint_after
    assert args.candidate_map.is_file() and args.candidate_map.stat().st_size > 0
    assert args.published_map.is_file() and args.published_map.stat().st_size > 0
    assert lifecycle["preexisting_unreal_processes"] == []
    assert lifecycle["source_sha256_before"] == lifecycle["source_sha256_after"]
    assert lifecycle["discard_probe"]["candidate_existed_after_discard"] is False
    assert lifecycle["final_candidate_restored"] is True

    result = {
        "schema_id": "scene-execution-verification/1",
        "verified": True,
        "stage_id": execution.stage_id,
        "source_sha256": sha256(args.source_map),
        "candidate_beauty_sha256": sha256(beauty),
        "generated_instance_count": execution.operations[1].generated_instance_count,
        "reconciled_instance_count": reconcile.operations[1].generated_instance_count,
        "publish_without_source_overwrite": True,
        "discard_probe_removed_only_candidate": True,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
