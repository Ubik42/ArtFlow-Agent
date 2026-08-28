from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from PIL import Image, ImageStat

from artflow_agent.scene_lifecycle import (
    DomainCorrectionPlan,
    LightingPatchReceipt,
    LightingPatchRequest,
    SceneDeltaEvaluation,
    SceneLifecycleLedger,
    VerifiedDispositionReceipt,
    VerifiedDispositionRequest,
    canonical_sha256,
)


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def luma(path: Path) -> float:
    with Image.open(path) as image:
        return float(ImageStat.Stat(image.convert("L")).mean[0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--candidate-map", type=Path, required=True)
    parser.add_argument("--published-map", type=Path, required=True)
    args = parser.parse_args()
    root = args.evidence_dir.resolve()
    failure_request = LightingPatchRequest.model_validate_json(
        (root / "failure-lighting-request.json").read_text(encoding="utf-8")
    )
    failure_receipt = LightingPatchReceipt.model_validate_json(
        (root / "failure-lighting-receipt.json").read_text(encoding="utf-8")
    )
    failure_evaluation = SceneDeltaEvaluation.model_validate_json(
        (root / "failure-evaluation.json").read_text(encoding="utf-8")
    )
    correction = DomainCorrectionPlan.model_validate_json(
        (root / "correction-plan.json").read_text(encoding="utf-8")
    )
    correction_request = LightingPatchRequest.model_validate_json(
        (root / "correction-lighting-request.json").read_text(encoding="utf-8")
    )
    correction_receipt = LightingPatchReceipt.model_validate_json(
        (root / "correction-lighting-receipt.json").read_text(encoding="utf-8")
    )
    corrected_evaluation = SceneDeltaEvaluation.model_validate_json(
        (root / "corrected-evaluation.json").read_text(encoding="utf-8")
    )
    disposition_request = VerifiedDispositionRequest.model_validate_json(
        (root / "disposition-request.json").read_text(encoding="utf-8")
    )
    publish = VerifiedDispositionReceipt.model_validate_json(
        (root / "disposition-receipt.json").read_text(encoding="utf-8")
    )
    replay = VerifiedDispositionReceipt.model_validate_json(
        (root / "disposition-reconcile-receipt.json").read_text(encoding="utf-8")
    )
    reconciliation = json.loads(
        (root / "correction-reconciliation.json").read_text(encoding="utf-8")
    )
    failure_capture = json.loads(
        (root / "failure-multi-view-receipt.json").read_text(encoding="utf-8")
    )
    corrected_capture = json.loads(
        (root / "corrected-multi-view-receipt.json").read_text(encoding="utf-8")
    )

    assert failure_request.purpose == "failure_fixture"
    assert failure_receipt.request_sha256 == failure_request.request_sha256
    assert failure_evaluation.failed_domains == ["lighting"]
    assert {item.domain for item in failure_evaluation.findings if item.verdict == "fail"} == {
        "lighting"
    }
    assert correction.failed_domains == correction.rerun_domains == ["lighting"]
    assert set(correction.preserved_domain_evidence) == {"asset", "material", "pcg"}
    assert correction_request.correction_plan_sha256 == correction.plan_sha256
    assert correction_receipt.request_sha256 == correction_request.request_sha256
    assert correction_receipt.generated_instance_count_before == 12
    assert correction_receipt.generated_instance_count_after == 12
    assert correction_receipt.material_path_before == correction_receipt.material_path_after
    assert corrected_evaluation.status == "verified" and not corrected_evaluation.failed_domains
    assert reconciliation["external_submission_count_during_reconcile"] == 0
    assert failure_capture["request_sha256"] == failure_request.request_sha256
    assert corrected_capture["request_sha256"] == correction_request.request_sha256
    assert publish.disposition == replay.disposition == "published"
    assert publish.published_scene_path == replay.published_scene_path
    assert publish.published_scene_sha256 == replay.published_scene_sha256
    assert publish.duplicate_side_effect_count == replay.duplicate_side_effect_count == 0
    assert disposition_request.evaluation_sha256 == corrected_evaluation.evaluation_sha256
    assert publish.evaluation_sha256 == corrected_evaluation.evaluation_sha256
    assert file_sha(args.source_map) == publish.source_scene_sha256_after
    assert file_sha(args.candidate_map) == disposition_request.candidate_scene_sha256
    assert file_sha(args.published_map) == publish.published_scene_sha256

    events = SceneLifecycleLedger(root / "lifecycle.sqlite3").events()
    expected_events = [
        "run_created",
        "evaluation_recorded",
        "correction_reserved",
        "correction_submitted",
        "correction_receipt_recorded",
        "verification_recorded",
        "disposition_reserved",
        "disposition_submitted",
        "disposition_receipt_recorded",
    ]
    assert [item.event_type for item in events] == expected_events
    (root / "event-stream.json").write_text(
        json.dumps([item.model_dump(mode="json") for item in events], ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    failure_luma = luma(root / "failure-authored-camera.png")
    corrected_luma = luma(root / "corrected-authored-camera.png")
    assert corrected_luma >= 145 > failure_luma
    with sqlite3.connect(root / "lifecycle.sqlite3") as connection:
        event_rows = connection.execute("SELECT COUNT(*) FROM scene_lifecycle_events").fetchone()[0]
    result = {
        "schema_id": "m9-s3-independent-verification/1",
        "status": "verified",
        "failed_domains_before": ["lighting"],
        "failed_domains_after": [],
        "rerun_domains": ["lighting"],
        "preserved_domains": ["asset", "material", "pcg"],
        "failure_authored_mean_luma": round(failure_luma, 6),
        "corrected_authored_mean_luma": round(corrected_luma, 6),
        "pcg_instances_before": correction_receipt.generated_instance_count_before,
        "pcg_instances_after": correction_receipt.generated_instance_count_after,
        "correction_reconcile_external_submissions": 0,
        "durable_event_count": event_rows,
        "published_scene_path": publish.published_scene_path,
        "published_scene_sha256": publish.published_scene_sha256,
        "publish_replay_duplicate_side_effects": 0,
        "source_scene_unchanged": True,
    }
    result["verification_sha256"] = canonical_sha256(result)
    (root / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
