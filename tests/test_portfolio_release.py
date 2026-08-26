from __future__ import annotations

import json
import zipfile
from pathlib import Path

from artflow_agent.portfolio_release import (
    build_release_archive,
    verify_release_archive,
)


def test_release_is_deterministic_and_tamper_detection_is_fail_closed(
    tmp_path: Path,
) -> None:
    run_id = "run-portfolio"
    fixtures = {
        "evidence/portfolio-summary.json": {"run_id": run_id, "event_count": 25},
        "evidence/harness-scorecard.json": {
            "run_id": run_id,
            "passed_cases": 20,
            "total_cases": 20,
        },
        "evidence/recovery-scorecard.json": {
            "passed_cases": 6,
            "total_cases": 6,
            "duplicate_side_effect_count": 0,
        },
        "evidence/memory-scorecard.json": {
            "passed_cases": 6,
            "total_cases": 6,
        },
        "evidence/verified-delivery.json": {
            "run_id": run_id,
            "delivery_sha256": "d" * 64,
        },
        "evidence/provenance-verification.json": {
            "status": "passed_with_declared_limitations",
            "hash_chain_valid": True,
            "verified_bindings": 9,
            "total_bindings": 9,
            "c2pa_signature_status": "not_present",
        },
    }
    generated = {
        name: (json.dumps(value, indent=2) + "\n").encode()
        for name, value in fixtures.items()
    }
    first, manifest = build_release_archive(
        output_root=tmp_path,
        release_id="fixture-release",
        run_id=run_id,
        event_count=25,
        sources=[],
        generated_files=generated,
        identities={"verified_delivery_sha256": "d" * 64},
        metrics={"harness": "20/20"},
        limitations=["unsigned C2PA sidecar"],
    )
    first_bytes = first.read_bytes()
    second, second_manifest = build_release_archive(
        output_root=tmp_path,
        release_id="fixture-release",
        run_id=run_id,
        event_count=25,
        sources=[],
        generated_files=generated,
        identities={"verified_delivery_sha256": "d" * 64},
        metrics={"harness": "20/20"},
        limitations=["unsigned C2PA sidecar"],
    )
    assert first == second
    assert first_bytes == second.read_bytes()
    assert manifest == second_manifest
    assert verify_release_archive(first).status == "passed"

    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(first) as source, zipfile.ZipFile(tampered, "w") as target:
        for info in source.infolist():
            content = source.read(info.filename)
            if info.filename == "evidence/harness-scorecard.json":
                content += b"tamper"
            target.writestr(info, content)
    result = verify_release_archive(tampered)
    assert result.status == "failed"
    assert "file_hash_mismatch:evidence/harness-scorecard.json" in result.failures
