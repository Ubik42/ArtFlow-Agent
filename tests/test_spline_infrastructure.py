import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.spline_infrastructure import (
    RouteCorridorReceipt,
    SplineInfrastructureRequest,
    file_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/goal/m49-s1-spline-infrastructure"


def test_spline_infrastructure_chain_is_content_bound_and_reconciled() -> None:
    request = SplineInfrastructureRequest.model_validate_json(
        (EVIDENCE / "spline-infrastructure-request.json").read_text(encoding="utf-8")
    )
    corridor = RouteCorridorReceipt.model_validate_json(
        (EVIDENCE / "comfy-route-corridor-receipt.json").read_text(encoding="utf-8")
    )
    blender = json.loads(
        (EVIDENCE / "blender-spline-infrastructure-receipt.json").read_text(encoding="utf-8")
    )
    unreal = json.loads(
        (EVIDENCE / "unreal-spline-infrastructure-receipt.json").read_text(encoding="utf-8")
    )

    assert corridor.request_sha256 == request.request_sha256
    assert corridor.protected_leakage == 0
    assert blender["corridor_receipt_sha256"] == corridor.receipt_sha256
    assert blender["route_count"] == 2
    assert blender["control_point_count"] == 14
    for artifact in blender["artifacts"]:
        assert file_sha256(EVIDENCE / artifact["relative_path"]) == artifact["sha256"]
    assert unreal["blender_receipt_sha256"] == blender["receipt_sha256"]
    assert unreal["status"] == "reconciled"
    assert unreal["spline_component_count"] == 2
    assert unreal["segment_actor_count"] == 12
    assert unreal["support_actor_count"] == 8
    assert unreal["created_actor_count"] == 0
    assert unreal["duplicate_side_effect_count"] == 0
    assert unreal["source_candidate_sha256_before"] == unreal["source_candidate_sha256_after"]

    changed = request.model_dump(mode="json")
    changed["max_total_segments"] = 15
    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        SplineInfrastructureRequest.model_validate(changed)
