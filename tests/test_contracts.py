import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.contracts import ProviderCapabilityManifest, SceneConstraintPackage


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

