from __future__ import annotations

import json
from pathlib import Path

from artflow_agent.provenance import (
    ProvenanceManifest,
    UnrealReturnReceipt,
    UnrealReturnRequest,
    verify_provenance,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "artifacts/goal/m6-s1-unreal-return"


def main() -> None:
    request = UnrealReturnRequest.model_validate_json(
        (OUTPUT_ROOT / "unreal-return-request.json").read_text(encoding="utf-8")
    )
    receipt = UnrealReturnReceipt.model_validate_json(
        (OUTPUT_ROOT / "unreal-return-receipt.json").read_text(encoding="utf-8")
    )
    manifest = ProvenanceManifest.model_validate_json(
        (OUTPUT_ROOT / "provenance-manifest.json").read_text(encoding="utf-8")
    )
    report = verify_provenance(manifest, request, receipt, ROOT)
    (OUTPUT_ROOT / "independent-verification.json").write_text(
        json.dumps(report.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    if report.status == "failed":
        raise RuntimeError(f"Provenance verification failed: {report.failures}")
    print(
        f"STATUS={report.status} HASH_CHAIN={str(report.hash_chain_valid).lower()} "
        f"BINDINGS={report.verified_bindings}/{report.total_bindings} "
        f"C2PA_SIGNATURE={report.c2pa_signature_status} MANIFEST={manifest.manifest_sha256}"
    )


if __name__ == "__main__":
    main()
