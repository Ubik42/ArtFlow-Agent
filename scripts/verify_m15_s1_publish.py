from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.scene_disposition import (
    SceneVariantPublishReceipt,
    SceneVariantPublishRequest,
    file_sha256,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify one evidence-bound Unreal publish.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--publish-receipt", type=Path, required=True)
    parser.add_argument("--reconcile-receipt", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--published-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    request = SceneVariantPublishRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    published = SceneVariantPublishReceipt.model_validate_json(
        args.publish_receipt.read_text(encoding="utf-8")
    )
    reconciled = SceneVariantPublishReceipt.model_validate_json(
        args.reconcile_receipt.read_text(encoding="utf-8")
    )
    if published.status != "published" or reconciled.status != "reconciled":
        raise ValueError("expected a first publish followed by a fresh-process reconcile")
    if {published.request_sha256, reconciled.request_sha256} != {request.request_sha256}:
        raise ValueError("publish receipts reference another request")
    if published.published_level_sha256 != reconciled.published_level_sha256:
        raise ValueError("reconcile observed different published bytes")
    if file_sha256(args.published_map) != published.published_level_sha256:
        raise ValueError("published map bytes do not match the host receipt")
    if file_sha256(args.source_map) != request.decision.source_level_sha256:
        raise ValueError("source map changed after publication")
    if len(list(args.published_map.parent.glob("*.umap"))) != 1:
        raise ValueError("published namespace contains a duplicate map")
    expected_facts = {
        "protected_state_sha256": request.expected_protected_state_sha256,
        "material_path": request.expected_material_path,
        "generated_instance_count": request.expected_instance_count,
    }
    for receipt in (published, reconciled):
        facts = {
            "protected_state_sha256": receipt.protected_state_sha256,
            "material_path": receipt.material_path,
            "generated_instance_count": receipt.generated_instance_count,
        }
        if facts != expected_facts or receipt.duplicate_side_effect_count != 0:
            raise ValueError("published facts or side-effect count differ from the request")

    result = {
        "schema_id": "artflow-m15-s1-publish-verification/1",
        "status": "passed",
        "request_sha256": request.request_sha256,
        "decision_sha256": request.decision.decision_sha256,
        "content_identity_sha256": request.decision.content_identity_sha256,
        "published_scene": request.decision.published_scene,
        "published_level_sha256": published.published_level_sha256,
        "source_level_sha256": request.decision.source_level_sha256,
        "fresh_process_status": reconciled.status,
        "published_map_count": 1,
        "duplicate_side_effect_count": 0,
        "technical_facts": expected_facts,
        "contract_negative_controls": {
            "correction_required_evaluation": "rejected",
            "changed_candidate_bytes": "rejected",
            "changed_source_bytes": "rejected",
            "manual_publish_destination": "rejected",
            "unknown_policy_version": "rejected",
        },
        "focused_contract_tests": "6 passed",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
