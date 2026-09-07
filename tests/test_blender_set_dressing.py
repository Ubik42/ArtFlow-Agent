from pathlib import Path

import pytest

from artflow_agent.blender_set_dressing import compile_set_dressing_request


def test_set_dressing_request_is_bounded_and_content_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    surface = root / "artifacts/goal/m26-s1-surface-bake"
    request = compile_set_dressing_request(
        session_id="scene-session-dc31f6ed0f4e",
        session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
        source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
        surface_request_path=surface / "surface-request.json",
        surface_receipt_path=surface / "surface-receipt.json",
        source_blend_path=surface / "AF_ShrineCourtyard_Baked.blend",
    )
    assert request.object_count == 12
    assert request.frame_end == 96
    with pytest.raises(ValueError, match="fingerprint"):
        request.__class__.model_validate({**request.model_dump(), "frame_end": 120})
