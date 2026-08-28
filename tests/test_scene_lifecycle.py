from __future__ import annotations

from datetime import UTC, datetime

import pytest

from artflow_agent.scene_lifecycle import (
    DomainCorrectionPlan,
    SceneLifecycleLedger,
    canonical_sha256,
)


def correction_payload() -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": "domain-correction-plan/1",
        "correction_id": "m9-correction-" + "1" * 20,
        "evaluation_sha256": "2" * 64,
        "failed_domains": ["lighting"],
        "rerun_domains": ["lighting"],
        "preserved_domain_evidence": {"asset": "3" * 64, "material": "4" * 64, "pcg": "5" * 64},
        "lighting": {"intensity": 8.0, "temperature_kelvin": 4200.0},
        "idempotency_key": "m9:correction:" + "6" * 32,
    }
    payload["plan_sha256"] = canonical_sha256(payload)
    return payload


def test_correction_scope_is_exactly_failed_domains() -> None:
    DomainCorrectionPlan.model_validate(correction_payload())
    widened = correction_payload()
    widened["rerun_domains"] = ["lighting", "pcg"]
    widened["plan_sha256"] = canonical_sha256({k: v for k, v in widened.items() if k != "plan_sha256"})
    with pytest.raises(ValueError, match="only failed domains"):
        DomainCorrectionPlan.model_validate(widened)


def test_append_only_lifecycle_replays_without_duplicate_side_effect(tmp_path) -> None:
    ledger = SceneLifecycleLedger(tmp_path / "lifecycle.sqlite3")
    events = [
        ("run_created", "run:m9", {"candidate": "/Game/ArtFlow/Staging/AF_test"}),
        ("evaluation_recorded", "evaluation:1", {"failed_domains": ["lighting"]}),
        ("correction_reserved", "correction:reserve", {"idempotency_key": "correction:1"}),
        ("correction_submitted", "correction:submit", {"external_operation": "ue-commandlet-1"}),
        ("correction_receipt_recorded", "correction:receipt", {"receipt_sha256": "a" * 64}),
        ("verification_recorded", "verification:1", {"failed_domains": []}),
        ("disposition_reserved", "publish:reserve", {"published_path": "/Game/ArtFlow/Published/AF_test"}),
        ("disposition_submitted", "publish:submit", {"external_operation": "ue-commandlet-2"}),
        ("disposition_receipt_recorded", "publish:receipt", {"receipt_sha256": "b" * 64}),
    ]
    for event_type, key, payload in events:
        ledger.append(event_type, key, payload)  # type: ignore[arg-type]
    prior = ledger.events()
    replay = ledger.append("disposition_receipt_recorded", "publish:receipt", {"receipt_sha256": "b" * 64})
    assert replay.sequence == 9
    assert SceneLifecycleLedger(ledger.path).events() == prior
    assert len(prior) == 9


def test_lifecycle_rejects_submit_before_durable_reservation(tmp_path) -> None:
    ledger = SceneLifecycleLedger(tmp_path / "lifecycle.sqlite3")
    ledger.append("run_created", "run:m9", {"created_at": datetime.now(UTC).isoformat()})
    with pytest.raises(ValueError, match="illegal lifecycle transition"):
        ledger.append("correction_submitted", "correction:submit", {})
