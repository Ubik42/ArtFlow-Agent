from __future__ import annotations

import pytest
from pydantic import ValidationError

from artflow_agent.blender_modeling import compile_weathered_shrine_request


def test_blender_modeling_request_is_deterministic_and_rejects_extra_authority() -> None:
    values = {
        "session_id": "scene-session-dc31f6ed0f4e",
        "session_sha256": "d" * 64,
        "source_scene": "/Game/ArtFlowDemo",
        "source_level_sha256": "6" * 64,
        "width_cm": 360,
        "depth_cm": 240,
        "height_cm": 320,
        "tier_count": 3,
        "pillar_count": 4,
        "detail_level": 3,
        "seed": 240907,
        "palette": "basalt_moss",
        "output_stem": "AF_WeatheredShrine",
    }
    first = compile_weathered_shrine_request(**values)
    assert compile_weathered_shrine_request(**values) == first
    with pytest.raises(ValidationError):
        first.__class__.model_validate({**first.model_dump(), "python": "bpy.ops.wm.quit_blender()"})
