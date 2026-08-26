import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.contracts import (
    ApprovalGrant,
    ProviderCapabilityManifest,
    ProviderExecutionReceipt,
    RouteDecision,
    SceneConstraintPackage,
)


def test_scene_constraint_fixture_enforces_portable_complete_passes() -> None:
    fixture = Path(__file__).parents[1] / "examples" / "scene-constraint-package.example.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    package = SceneConstraintPackage.model_validate(payload)

    assert package.schema_id == "scene-constraint-package/1"
    assert {item.kind for item in package.passes} == {
        "beauty",
        "depth",
        "world_normal",
        "object_id",
    }

    payload["passes"][0]["artifact"]["path"] = "../outside.png"
    with pytest.raises(ValidationError, match="package-relative"):
        SceneConstraintPackage.model_validate(payload)


def test_scene_constraint_rejects_missing_or_duplicate_passes() -> None:
    fixture = Path(__file__).parents[1] / "examples" / "scene-constraint-package.example.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    payload["passes"][3]["kind"] = "beauty"

    with pytest.raises(ValidationError, match="render pass kinds must be unique"):
        SceneConstraintPackage.model_validate(payload)


def test_hosted_provider_cannot_bypass_cost_approval() -> None:
    payload = {
        "provider_id": "gpt-image",
        "display_name": "GPT Image",
        "execution_kind": "hosted",
        "privacy_class": "provider_processed",
        "cost_class": "metered",
        "requires_explicit_cost_approval": False,
        "models": [
            {
                "model_id": "gpt-image-2",
                "model_version": "provider-current",
                "tasks": ["scene_direction", "masked_refinement"],
                "controls": ["reference_image", "mask", "multi_turn_edit"],
            }
        ],
    }

    with pytest.raises(ValidationError, match="explicit cost approval"):
        ProviderCapabilityManifest.model_validate(payload)


def test_hosted_approval_is_bound_to_route_cost_privacy_model_and_input() -> None:
    decision = RouteDecision(
        decision_id="route-001",
        scene_package_id="scene-001",
        scene_package_sha256="a" * 64,
        task="scene_direction",
        selected={
            "provider_id": "comfy-local",
            "model_id": "flux-dev",
            "execution_kind": "local",
            "privacy_class": "local_only",
            "cost_class": "local_compute",
        },
        execution_intent={
            "required_controls": ["reference_image", "depth"],
            "output_count": 1,
            "width": 1280,
            "height": 720,
            "delivery_format": "png",
            "intent_sha256": "d" * 64,
        },
        privacy_ceiling="local_only",
        max_cost_usd=0,
        requires_explicit_approval=True,
        rationale="Use the available offline GPU route.",
    )
    approved_at = datetime(2026, 8, 25, tzinfo=UTC)
    grant = ApprovalGrant(
        approval_id="approval-001",
        route_decision_id=decision.decision_id,
        route_fingerprint=decision.approval_fingerprint(),
        approved_by="portfolio-owner",
        approved_at=approved_at,
        expires_at=approved_at + timedelta(hours=1),
    )

    assert grant.authorizes(decision, at=approved_at + timedelta(minutes=30))

    hosted = decision.model_copy(
        update={
            "selected": decision.selected.model_copy(
                update={
                    "provider_id": "gpt-image",
                    "model_id": "gpt-image-2",
                    "execution_kind": "hosted",
                    "privacy_class": "provider_processed",
                    "cost_class": "metered",
                }
            )
        }
    )
    assert not grant.authorizes(hosted, at=approved_at + timedelta(minutes=30))
    changed_cost = decision.model_copy(update={"max_cost_usd": 1})
    changed_intent = decision.model_copy(
        update={
            "execution_intent": decision.execution_intent.model_copy(
                update={"output_count": 2}
            )
        }
    )
    assert not grant.authorizes(changed_cost, at=approved_at + timedelta(minutes=30))
    assert not grant.authorizes(changed_intent, at=approved_at + timedelta(minutes=30))
    assert not grant.authorizes(decision, at=approved_at + timedelta(hours=2))

    unapproved_payload = hosted.model_dump()
    unapproved_payload["requires_explicit_approval"] = False
    with pytest.raises(ValidationError, match="require explicit approval"):
        RouteDecision.model_validate(unapproved_payload)


def test_provider_receipt_fails_closed_for_invalid_outcome_or_path() -> None:
    base = {
        "execution_id": "execution-001",
        "route_decision_id": "route-001",
        "route_fingerprint": "b" * 64,
        "provider_id": "comfy-local",
        "model_id": "flux-dev",
        "status": "succeeded",
        "started_at": "2026-08-25T12:00:00Z",
        "completed_at": "2026-08-25T12:01:00Z",
        "artifacts": [
            {"path": "artifacts/result.png", "sha256": "c" * 64, "media_type": "image/png"}
        ],
    }
    receipt = ProviderExecutionReceipt.model_validate(base)
    assert receipt.status == "succeeded"

    base["artifacts"][0]["path"] = "../result.png"
    with pytest.raises(ValidationError, match="must not escape"):
        ProviderExecutionReceipt.model_validate(base)
