from __future__ import annotations

import json
from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.provenance import (
    ProvenanceManifest,
    ProvenanceVerification,
    UnrealReturnReceipt,
    VerifiedDeliveryRecord,
    canonical_sha256,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "artifacts/goal/m6-s1-unreal-return"
RUN_ROOT = ROOT / "artifacts/goal/m3-s11-local-run"
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def main() -> None:
    receipt = UnrealReturnReceipt.model_validate_json(
        (OUTPUT_ROOT / "unreal-return-receipt.json").read_text(encoding="utf-8")
    )
    manifest = ProvenanceManifest.model_validate_json(
        (OUTPUT_ROOT / "provenance-manifest.json").read_text(encoding="utf-8")
    )
    report_path = OUTPUT_ROOT / "independent-verification.json"
    report = ProvenanceVerification.model_validate_json(
        report_path.read_text(encoding="utf-8")
    )
    if report.status != "passed_with_declared_limitations" or not report.hash_chain_valid:
        raise RuntimeError("Only an independently verified hash chain may be recorded")
    payload = {
        "schema_id": "artflow-verified-delivery/1",
        "run_id": RUN_ID,
        "return_receipt": receipt.model_dump(mode="json"),
        "provenance_manifest_sha256": manifest.manifest_sha256,
        "verification_report_sha256": sha256_file(report_path),
        "visible_evidence_sha256": sha256_file(OUTPUT_ROOT / "unreal-return-visible.png"),
        "status": "verified_with_declared_c2pa_limitation",
        "delivery_sha256": "0" * 64,
    }
    payload["delivery_sha256"] = canonical_sha256(payload, "delivery_sha256")
    delivery = VerifiedDeliveryRecord.model_validate(payload)
    store = AgentEventStore(RUN_ROOT / "agent-events.sqlite3")
    state = store.record_verified_delivery(RUN_ID, delivery)
    (OUTPUT_ROOT / "verified-delivery.json").write_text(
        json.dumps(delivery.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"EVENTS={state.last_sequence} DELIVERY={delivery.delivery_sha256} "
        f"C2PA_SIGNATURE={report.c2pa_signature_status}"
    )


if __name__ == "__main__":
    main()
