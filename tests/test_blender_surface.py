from pathlib import Path

import pytest

from artflow_agent.blender_surface import compile_surface_request


def test_surface_request_is_content_bound() -> None:
    root = Path(__file__).resolve().parents[1]
    lookdev = root / "artifacts/goal/m24-s2-scene-lookdev"
    request = compile_surface_request(
        session_id="scene-session-dc31f6ed0f4e",
        session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
        source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
        lookdev_request_path=lookdev / "lookdev-request.json",
        lookdev_receipt_path=lookdev / "lookdev-receipt.json",
        source_blend_path=lookdev / "AF_ShrineCourtyard_Lookdev.blend",
        objects=[
            {"name": "AF_GN_ShrineCourtyard", "source": "geometry_nodes_output"},
            {"name": "AF_Altar", "source": "registered_mesh"},
        ],
    )
    assert request.atlas_resolution == 1024
    assert request.bake_channels == ["base_color", "roughness"]
    with pytest.raises(ValueError, match="fingerprint"):
        request.__class__.model_validate({**request.model_dump(), "margin_px": 32})
