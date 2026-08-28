from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.multi_domain_unreal import MultiDomainUnrealRequest, canonical_sha256

ROOT = Path(__file__).resolve().parents[1]


def request_payload() -> dict[str, object]:
    path = ROOT / "artifacts" / "goal" / "m9-s2-unreal-multi-domain" / "unreal-request.json"
    return json.loads(path.read_text(encoding="utf-8"))


def resign(payload: dict[str, object]) -> dict[str, object]:
    value = dict(payload)
    value.pop("request_sha256", None)
    value["request_sha256"] = canonical_sha256(value)
    return value


def test_request_is_bound_to_real_four_domain_inputs() -> None:
    request = MultiDomainUnrealRequest.model_validate(request_payload())
    assert request.operation_order == [
        "asset-reuse",
        "lighting-patch",
        "material-bind",
        "pcg-layout",
    ]
    assert request.pcg.expected_instance_count == 12
    assert request.material.material_instance_path.endswith("MI_RuinAltarBasalt.MI_RuinAltarBasalt")
    assert {item.role for item in request.actors} == {
        "editable", "protected", "key_light", "authored_camera"
    }


def test_request_rejects_reordered_writes_and_hash_tamper() -> None:
    value = request_payload()
    value["operation_order"] = list(reversed(value["operation_order"]))
    with pytest.raises(ValidationError, match="operation order"):
        MultiDomainUnrealRequest.model_validate(resign(value))

    value = request_payload()
    value["lighting"]["intensity"] = 999
    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        MultiDomainUnrealRequest.model_validate(value)


def test_request_rejects_external_asset_and_duplicate_actor_role() -> None:
    value = request_payload()
    value["asset"]["asset_paths"] = ["/Engine/BasicShapes/Cube"]
    with pytest.raises(ValidationError, match="ArtFlow project assets"):
        MultiDomainUnrealRequest.model_validate(resign(value))

    value = request_payload()
    value["actors"][0]["role"] = "protected"
    with pytest.raises(ValidationError, match="exactly four required actor roles"):
        MultiDomainUnrealRequest.model_validate(resign(value))
