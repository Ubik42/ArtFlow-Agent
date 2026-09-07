from pathlib import Path

import pytest

from artflow_agent.cloth_banner import ClothBannerRequest, compile_cloth_banner_request


def test_cloth_banner_request_is_scene_bound_and_tamper_evident() -> None:
    root = Path(__file__).resolve().parents[1]
    request = compile_cloth_banner_request(root=root, session_id="scene-session-dc31f6ed0f4e")
    assert request.source_candidate_scene_path.endswith("/Damage_B_fdfe74fd21b1")
    assert request.blender_capability_id == "blender.cloth.banner_authoring.v1"
    assert request.frame_end == 48
    assert sum(v * v for v in request.wind_direction) == pytest.approx(1.0, abs=1e-5)

    changed = request.model_dump(mode="json")
    changed["wind_strength"] = 900.0
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        ClothBannerRequest.model_validate(changed)
