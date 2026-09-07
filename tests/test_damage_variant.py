from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.damage_variant import compile_damage_variant_request

ROOT = Path(__file__).resolve().parents[1]


def test_damage_variant_request_binds_registered_source_and_budgets() -> None:
    request = compile_damage_variant_request(
        root=ROOT, session_id="scene-session-dc31f6ed0f4e"
    )

    assert request.source_candidate_scene_path.endswith("Modular_B_991e0fa20ff4")
    assert request.target_object == "SM_AF_Module_Gateway"
    assert request.target_actor_label == "ArtFlow_Module_module-placement-05"
    assert request.chip_count == 7
    assert request.triangle_budget == 6000

    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        request.model_copy(update={"chip_count": 12}).model_validate(
            request.model_copy(update={"chip_count": 12}).model_dump()
        )
