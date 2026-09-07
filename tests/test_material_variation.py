from pathlib import Path

import pytest

from artflow_agent.material_variation import compile_material_variation_request

ROOT = Path(__file__).resolve().parents[1]


def test_material_variation_request_binds_current_hosts() -> None:
    request = compile_material_variation_request(
        conditioning_receipt_path=ROOT
        / "artifacts/goal/m24-s1-scene-conditioning/conditioning-receipt.json",
        procedural_kit_receipt_path=ROOT
        / "artifacts/goal/m32-s1-procedural-kit/procedural-kit-receipt.json",
        native_pcg_receipt_path=ROOT
        / "artifacts/goal/m34-s1-pcg-density/unreal-native-pcg-density-receipt.json",
        session_id="scene-session-dc31f6ed0f4e",
        session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
    )
    assert request.source_candidate_scene_path.endswith("Density_B_1a637a8d89b8")
    assert [item.variant_id for item in request.palettes] == [
        "wayfinder-a",
        "wayfinder-b",
        "wayfinder-c",
    ]

    payload = request.model_dump(mode="json")
    payload["palettes"][0]["base_tint"][0] = 1.2
    with pytest.raises(ValueError, match="normalized RGB"):
        request.__class__.model_validate(payload)
