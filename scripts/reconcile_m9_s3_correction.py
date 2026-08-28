from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.scene_lifecycle import (
    LightingPatchReceipt,
    LightingPatchRequest,
    SceneLifecycleLedger,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile an already-submitted UE correction without resubmitting it."
    )
    parser.add_argument("database", type=Path)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = LightingPatchRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    receipt = LightingPatchReceipt.model_validate_json(args.receipt.read_text(encoding="utf-8"))
    if receipt.request_id != request.request_id or receipt.request_sha256 != request.request_sha256:
        raise ValueError("external receipt does not bind the submitted correction request")
    ledger = SceneLifecycleLedger(args.database)
    events_before = ledger.events()
    if not events_before or events_before[-1].event_type not in {
        "correction_submitted", "correction_receipt_recorded"
    }:
        raise ValueError("no submitted correction is awaiting reconciliation")
    event = ledger.append(
        "correction_receipt_recorded",
        f"m9:correction:receipt:{receipt.receipt_sha256[:16]}",
        receipt.model_dump(mode="json"),
    )
    result = {
        "schema_id": "m9-correction-reconciliation/1",
        "status": "reconciled_without_resubmit",
        "event_sequence": event.sequence,
        "request_sha256": request.request_sha256,
        "receipt_sha256": receipt.receipt_sha256,
        "external_submission_count_during_reconcile": 0,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
