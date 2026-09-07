from pathlib import Path

from artflow_agent.camera_move import CameraMoveRequest


def test_camera_move_binds_current_shot_and_three_finite_poses() -> None:
    root = Path(__file__).parents[1]
    restored = CameraMoveRequest.model_validate_json(
        (root / "artifacts/goal/m38-s1-camera-move/camera-move-request.json").read_text(
            encoding="utf-8"
        )
    )
    assert restored.capability_id == "blender.camera_move.three_key_dolly.v1"
    assert [pose.frame for pose in restored.poses] == [0, 60, 119]
    assert [pose.label for pose in restored.poses] == ["start", "middle", "end"]
    assert restored.source_sequence_path.endswith("LS_AF_76936ac2cf65")
    assert restored.sequence_asset_path.startswith(
        "/Game/ArtFlow/Sequences/Generated/LS_AF_CameraMove_"
    )
