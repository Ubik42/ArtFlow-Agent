import json
from pathlib import Path

from artflow_agent.shot_package import ShotPackageRequest


def test_shot_package_request_binds_camera_lights_sequence_and_candidate() -> None:
    root = Path(__file__).parents[1]
    request = ShotPackageRequest.model_validate_json(
        (root / "artifacts/goal/m36-s1-shot-package/shot-package-request.json").read_text(
            encoding="utf-8"
        )
    )
    assert request.capability_id == "unreal.sequencer.procedural_environment_shot.v1"
    assert [item.role for item in request.light_rig] == ["key", "fill", "rim"]
    assert request.playback_end_frame - request.playback_start_frame == 120
    assert request.source_candidate_scene_path.endswith("Density_B_1a637a8d89b8")
    assert request.candidate_scene_path.endswith(request.sequence_asset_path.split("_")[-1])
    assert json.loads(request.model_dump_json())["display_rate_fps"] == 24
