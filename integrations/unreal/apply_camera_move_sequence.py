from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import unreal


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow camera move failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m38-s1-camera-move"
request = json.loads((evidence / "camera-move-request.json").read_text(encoding="utf-8"))
unsigned = dict(request)
unsigned.pop("request_sha256")
if canonical(unsigned) != request["request_sha256"]:
    fail("request fingerprint changed")
blender_receipt = json.loads(
    (evidence / "blender-camera-move-receipt.json").read_text(encoding="utf-8")
)
blender_unsigned = dict(blender_receipt)
blender_unsigned.pop("receipt_sha256")
if canonical(blender_unsigned) != blender_receipt["receipt_sha256"]:
    fail("Blender camera-move receipt changed")
if blender_receipt["request_sha256"] != request["request_sha256"]:
    fail("Blender camera move references another request")

project = Path(unreal.Paths.project_dir()).resolve()
content = project / "Content"
source_sequence_object = request["source_sequence_path"]
source_sequence_package = source_sequence_object.split(".", 1)[0]
source_sequence_file = content / (source_sequence_package.removeprefix("/Game/") + ".uasset")
source_candidate_package = request["source_candidate_scene_path"]
source_candidate_file = content / (source_candidate_package.removeprefix("/Game/") + ".umap")
if sha256(source_sequence_file) != request["source_sequence_sha256"]:
    fail("source Level Sequence identity changed")
if sha256(source_candidate_file) != request["source_candidate_sha256"]:
    fail("source shot candidate identity changed")
source_sequence_before = sha256(source_sequence_file)
source_candidate_before = sha256(source_candidate_file)

target_object = request["sequence_asset_path"]
target_package, target_name = target_object.rsplit(".", 1)
target_existed = unreal.EditorAssetLibrary.does_asset_exist(target_object)
if target_existed:
    sequence = unreal.EditorAssetLibrary.load_asset(target_object)
else:
    sequence = unreal.EditorAssetLibrary.duplicate_asset(source_sequence_package, target_package)
if not isinstance(sequence, unreal.LevelSequence):
    fail("could not create the camera-move Level Sequence")

recorded_request = unreal.EditorAssetLibrary.get_metadata_tag(
    sequence, "ArtFlow.CameraMoveRequestSha256"
)
if recorded_request not in {"", request["request_sha256"]}:
    fail("target Level Sequence belongs to another camera move")
configured = recorded_request == request["request_sha256"]
bindings = sequence.get_bindings()
camera_bindings = [
    binding for binding in bindings if str(binding.get_display_name()) == "ArtFlow_Sequence_Camera"
]
if len(camera_bindings) != 1:
    fail(f"expected one registered camera binding, got {len(camera_bindings)}")
camera_binding = camera_bindings[0]
transform_tracks = [
    track
    for track in camera_binding.get_tracks()
    if isinstance(track, unreal.MovieScene3DTransformTrack)
]
if not configured:
    if transform_tracks:
        fail("unregistered transform track already exists on the camera")
    transform_track = camera_binding.add_track(unreal.MovieScene3DTransformTrack)
    transform_section = transform_track.add_section()
    transform_section.set_range(request["playback_start_frame"], request["playback_end_frame"])
    channels = {
        str(channel.channel_name): channel for channel in transform_section.get_all_channels()
    }
    expected_channels = {
        "Location.X",
        "Location.Y",
        "Location.Z",
        "Rotation.X",
        "Rotation.Y",
        "Rotation.Z",
        "Scale.X",
        "Scale.Y",
        "Scale.Z",
    }
    if set(channels) != expected_channels:
        fail(f"unexpected transform channels: {sorted(channels)}")
    for pose in request["poses"]:
        pitch, yaw, roll = pose["rotation_deg"]
        values = {
            "Location.X": pose["location_cm"][0],
            "Location.Y": pose["location_cm"][1],
            "Location.Z": pose["location_cm"][2],
            "Rotation.X": roll,
            "Rotation.Y": pitch,
            "Rotation.Z": yaw,
            "Scale.X": 1.0,
            "Scale.Y": 1.0,
            "Scale.Z": 1.0,
        }
        for name, value in values.items():
            channels[name].add_key(
                time=unreal.FrameNumber(value=pose["frame"]),
                new_value=float(value),
                interpolation=unreal.MovieSceneKeyInterpolation.SMART_AUTO,
            )
    unreal.EditorAssetLibrary.set_metadata_tag(
        sequence, "ArtFlow.CameraMoveRequestSha256", request["request_sha256"]
    )
    unreal.EditorAssetLibrary.set_metadata_tag(
        sequence, "ArtFlow.SourceShotSequenceSha256", request["source_sequence_sha256"]
    )
    unreal.EditorAssetLibrary.save_loaded_asset(sequence, only_if_is_dirty=False)

transform_tracks = [
    track
    for track in camera_binding.get_tracks()
    if isinstance(track, unreal.MovieScene3DTransformTrack)
]
if len(transform_tracks) != 1:
    fail(f"camera transform track count changed: {len(transform_tracks)}")
sections = transform_tracks[0].get_sections()
if len(sections) != 1:
    fail(f"camera transform section count changed: {len(sections)}")
channels = {str(channel.channel_name): channel for channel in sections[0].get_all_channels()}
key_counts = {name: len(channel.get_keys()) for name, channel in channels.items()}
if any(count != 3 for count in key_counts.values()):
    fail(f"camera transform channel key count changed: {key_counts}")

world = unreal.EditorLoadingAndSavingUtils.load_map(source_candidate_package)
if world is None:
    fail("could not load shot-package candidate")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
camera = next(
    (actor for actor in actors if actor.get_actor_label() == "ArtFlow_Sequence_Camera"), None
)
if not isinstance(camera, unreal.CineCameraActor):
    fail("registered shot camera is unavailable")

preview_paths = {
    pose["label"]: evidence / f"unreal-camera-move-{pose['label']}.png" for pose in request["poses"]
}
for path in preview_paths.values():
    if path.is_file():
        path.unlink()

state = {"pose_index": 0, "ticks": 0, "callback": None}


def apply_pose(index: int) -> None:
    pose = request["poses"][index]
    camera.set_actor_location(unreal.Vector(*pose["location_cm"]), False, False)
    camera.set_actor_rotation(
        unreal.Rotator(
            pitch=pose["rotation_deg"][0],
            yaw=pose["rotation_deg"][1],
            roll=pose["rotation_deg"][2],
        ),
        False,
    )
    unreal.AutomationLibrary.take_high_res_screenshot(
        1280, 720, str(preview_paths[pose["label"]]), camera, False, False
    )


def finish(_delta_seconds: float) -> None:
    state["ticks"] += 1
    pose = request["poses"][state["pose_index"]]
    path = preview_paths[pose["label"]]
    if not path.is_file() and state["ticks"] <= 180:
        return
    if not path.is_file():
        fail(f"capture unavailable for {pose['label']}")
    if state["pose_index"] < len(request["poses"]) - 1:
        state["pose_index"] += 1
        state["ticks"] = 0
        apply_pose(state["pose_index"])
        return
    source_sequence_after = sha256(source_sequence_file)
    source_candidate_after = sha256(source_candidate_file)
    if source_sequence_after != source_sequence_before:
        fail("camera move changed the source Level Sequence")
    if source_candidate_after != source_candidate_before:
        fail("camera move changed the source shot candidate")
    target_file = content / (target_package.removeprefix("/Game/") + ".uasset")
    result = {
        "schema_id": "artflow-unreal-camera-move-receipt/1",
        "request_id": request["request_id"],
        "request_sha256": request["request_sha256"],
        "blender_receipt_sha256": blender_receipt["receipt_sha256"],
        "status": "reconciled" if target_existed and configured else "created",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "source_sequence_path": source_sequence_object,
        "source_sequence_sha256_before": source_sequence_before,
        "source_sequence_sha256_after": source_sequence_after,
        "source_candidate_scene_path": source_candidate_package,
        "source_candidate_sha256_before": source_candidate_before,
        "source_candidate_sha256_after": source_candidate_after,
        "sequence_asset_path": sequence.get_path_name(),
        "sequence_sha256": sha256(target_file),
        "camera_binding_count": len(camera_bindings),
        "transform_track_count": len(transform_tracks),
        "transform_section_count": len(sections),
        "transform_channel_count": len(channels),
        "keys_per_channel": key_counts,
        "frame_numbers": [pose["frame"] for pose in request["poses"]],
        "preview_paths": {label: path.name for label, path in preview_paths.items()},
        "preview_sha256s": {label: sha256(path) for label, path in preview_paths.items()},
        "duplicate_track_count": 0,
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-camera-move-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    unreal.log(
        f"ARTFLOW_CAMERA_MOVE status={result['status']} sequence={sequence.get_path_name()} keys=27"
    )
    unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


state["callback"] = unreal.register_slate_post_tick_callback(finish)
apply_pose(0)
unreal.log("ARTFLOW_CAMERA_MOVE_PENDING waiting for three registered frame captures")
