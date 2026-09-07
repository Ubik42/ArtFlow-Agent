import json
from pathlib import Path

import pytest

from artflow_agent.lookdev_handoff import SceneLookdevRequest, compile_scene_lookdev_request

ROOT = Path(__file__).resolve().parents[1]


def compile_request():
    conditioning = ROOT / "artifacts/goal/m24-s1-scene-conditioning"
    shot = ROOT / "artifacts/goal/m23-s5-camera-light"
    return compile_scene_lookdev_request(
        session_id="scene-session-dc31f6ed0f4e",
        session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
        source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
        conditioning_request_path=conditioning / "conditioning-request.json",
        conditioning_receipt_path=conditioning / "conditioning-receipt.json",
        accepted_artifact_path=conditioning / "depth-guided-candidate.png",
        shot_request_path=shot / "shot-request.json",
        source_blend_path=shot / "AF_ShrineCourtyard_Shot.blend",
    )


def test_compiler_binds_target_and_only_registered_slots():
    request = compile_request()
    assert [item.target for item in request.material_tints] == [
        "M_AF_Stone",
        "M_AF_Weathering",
        "M_AF_Inlay",
    ]
    assert [item.role for item in request.light_rig] == ["key", "fill", "rim"]
    assert (
        request.accepted_artifact_sha256
        == "0f65a7a7bb0f1bdd0bdf9ab41e2b9e3367d0c6a15be364a5b3b9e8ccc9ff41cb"
    )


def test_tampered_registered_target_fails_closed():
    payload = compile_request().model_dump(mode="json")
    payload["material_tints"][0]["target"] = "ArbitraryMaterial"
    with pytest.raises(ValueError):
        SceneLookdevRequest.model_validate(payload)


def test_tampered_identity_fails_closed():
    payload = json.loads(compile_request().model_dump_json())
    payload["light_rig"][0]["intensity_lux"] = 9.0
    with pytest.raises(ValueError, match="fingerprint"):
        SceneLookdevRequest.model_validate(payload)
