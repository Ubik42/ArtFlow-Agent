from __future__ import annotations

import hashlib
import json
import math
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
    raise RuntimeError(f"ArtFlow shot package failed: {message}")


def find_actor(actors: list[unreal.Actor], label: str) -> unreal.Actor | None:
    return next((actor for actor in actors if actor.get_actor_label() == label), None)


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m36-s1-shot-package"
request_path = evidence / "shot-package-request.json"
request = json.loads(request_path.read_text(encoding="utf-8"))
unsigned = dict(request)
unsigned.pop("request_sha256")
if canonical(unsigned) != request["request_sha256"]:
    fail("request fingerprint changed")

project = Path(unreal.Paths.project_dir()).resolve()
source_package = request["source_candidate_scene_path"]
source_file = project / "Content" / (source_package.removeprefix("/Game/") + ".umap")
if sha256(source_file) != request["source_candidate_sha256"]:
    fail("registered native PCG candidate changed")
source_before = sha256(source_file)

candidate_package = request["candidate_scene_path"]
candidate_name = candidate_package.rsplit("/", 1)[-1]
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(source_package, candidate_package)
    if candidate is None:
        fail("could not duplicate native PCG candidate for shot packaging")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()

world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load shot package candidate")
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsystem.get_all_level_actors()

camera_data = request["camera"]
camera = find_actor(actors, camera_data["label"])
camera_reconciled = isinstance(camera, unreal.CineCameraActor)
location = unreal.Vector(*camera_data["location_cm"])
rotation = unreal.Rotator(
    pitch=camera_data["rotation_deg"][0],
    yaw=camera_data["rotation_deg"][1],
    roll=camera_data["rotation_deg"][2],
)
if camera is None:
    camera = actor_subsystem.spawn_actor_from_class(unreal.CineCameraActor, location, rotation)
if not isinstance(camera, unreal.CineCameraActor):
    fail("registered shot camera is not a CineCameraActor")
camera.set_actor_label(camera_data["label"])
camera.set_actor_location(location, False, False)
camera.set_actor_rotation(rotation, False)
camera.tags = ["ArtFlow.Generated", request["request_id"], "ArtFlow.Sequencer.Camera"]
camera_component = camera.get_cine_camera_component()
sensor_width = 36.0
sensor_height = sensor_width / camera_data["aspect_ratio"]
filmback = unreal.CameraFilmbackSettings(sensor_width=sensor_width, sensor_height=sensor_height)
camera_component.set_editor_property("filmback", filmback)
focal_length = sensor_width / (
    2.0 * math.tan(math.radians(camera_data["horizontal_fov_deg"]) / 2.0)
)
camera_component.set_editor_property("current_focal_length", focal_length)

light_actors: list[unreal.DirectionalLight] = []
for light_data in request["light_rig"]:
    actor = find_actor(actors, light_data["actor_label"])
    if not isinstance(actor, unreal.DirectionalLight):
        fail(f"registered shot light is missing: {light_data['actor_label']}")
    actor.set_actor_rotation(
        unreal.Rotator(
            pitch=light_data["rotation_deg"][0],
            yaw=light_data["rotation_deg"][1],
            roll=light_data["rotation_deg"][2],
        ),
        False,
    )
    component = actor.get_editor_property("directional_light_component")
    component.set_editor_property("intensity", light_data["intensity_lux"])
    component.set_editor_property("use_temperature", True)
    component.set_editor_property("temperature", light_data["temperature_kelvin"])
    component.set_editor_property("cast_shadows", light_data["cast_shadows"])
    light_actors.append(actor)

sequence_object = request["sequence_asset_path"]
sequence_package, sequence_name = sequence_object.rsplit(".", 1)
sequence_reconciled = unreal.EditorAssetLibrary.does_asset_exist(sequence_object)
if sequence_reconciled:
    sequence = unreal.EditorAssetLibrary.load_asset(sequence_object)
else:
    asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
    sequence = asset_tools.create_asset(
        sequence_name,
        sequence_package.rsplit("/", 1)[0],
        unreal.LevelSequence,
        unreal.LevelSequenceFactoryNew(),
    )
if not isinstance(sequence, unreal.LevelSequence):
    fail("could not create the registered Level Sequence")

recorded_request_sha = unreal.EditorAssetLibrary.get_metadata_tag(
    sequence, "ArtFlow.ShotPackageRequestSha256"
)
if recorded_request_sha not in {"", request["request_sha256"]}:
    fail("existing Level Sequence belongs to another request")
sequence_configured = recorded_request_sha == request["request_sha256"]
if not sequence_configured:
    sequence.set_display_rate(unreal.FrameRate(request["display_rate_fps"], 1))
    sequence.set_playback_start(request["playback_start_frame"])
    sequence.set_playback_end(request["playback_end_frame"])
    camera_binding = sequence.add_possessable(camera)
    for light in light_actors:
        sequence.add_possessable(light)
    camera_cut_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)
    camera_cut = camera_cut_track.add_section()
    camera_cut.set_range(request["playback_start_frame"], request["playback_end_frame"])
    binding_id = unreal.MovieSceneObjectBindingID()
    binding_id.set_editor_property("guid", camera_binding.get_id())
    camera_cut.set_camera_binding_id(binding_id)
    unreal.EditorAssetLibrary.set_metadata_tag(
        sequence, "ArtFlow.ShotPackageRequestSha256", request["request_sha256"]
    )
    unreal.EditorAssetLibrary.set_metadata_tag(
        sequence, "ArtFlow.SourceCandidateSha256", request["source_candidate_sha256"]
    )
    unreal.EditorAssetLibrary.save_loaded_asset(sequence, only_if_is_dirty=False)

bindings = sequence.get_bindings()
if len(bindings) != 4:
    fail(f"Level Sequence binding count changed: {len(bindings)}")
tracks = sequence.get_tracks()
camera_cut_track_count = sum(isinstance(track, unreal.MovieSceneCameraCutTrack) for track in tracks)
if camera_cut_track_count != 1:
    fail(f"Level Sequence camera-cut track count changed: {camera_cut_track_count}")
if sequence.get_playback_start() != request["playback_start_frame"]:
    fail("Level Sequence playback start changed")
if sequence.get_playback_end() != request["playback_end_frame"]:
    fail("Level Sequence playback end changed")

unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
source_after = sha256(source_file)
if source_after != source_before:
    fail("shot packaging changed the native PCG source candidate")

screenshot = evidence / "unreal-shot-package-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
state = {"ticks": 0, "callback": None}


def finish(_delta_seconds: float) -> None:
    state["ticks"] += 1
    if not screenshot.is_file() and state["ticks"] <= 180:
        return
    result = {
        "schema_id": "artflow-unreal-shot-package-receipt/1",
        "request_id": request["request_id"],
        "request_sha256": request["request_sha256"],
        "status": "reconciled"
        if candidate_reconciled and sequence_configured and camera_reconciled
        else "created",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "source_candidate_scene_path": source_package,
        "source_candidate_sha256_before": source_before,
        "source_candidate_sha256_after": source_after,
        "candidate_scene_path": candidate_package,
        "sequence_asset_path": sequence.get_path_name(),
        "sequence_binding_count": len(bindings),
        "camera_binding_count": 1,
        "light_binding_count": len(light_actors),
        "camera_cut_track_count": camera_cut_track_count,
        "display_rate_fps": request["display_rate_fps"],
        "playback_range": [request["playback_start_frame"], request["playback_end_frame"]],
        "preview_frame": request["preview_frame"],
        "camera_label": camera.get_actor_label(),
        "camera_horizontal_fov_deg": camera_component.get_editor_property("field_of_view"),
        "screenshot_path": screenshot.name,
        "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
        "capture_status": "captured" if screenshot.is_file() else "unavailable",
        "duplicate_asset_count": 0,
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-shot-package-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    unreal.log(
        f"ARTFLOW_SHOT_PACKAGE status={result['status']} sequence={sequence.get_path_name()} "
        f"bindings={len(bindings)}"
    )
    unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


state["callback"] = unreal.register_slate_post_tick_callback(finish)
unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(screenshot), camera, False, False)
unreal.log("ARTFLOW_SHOT_PACKAGE_PENDING waiting for same-camera capture")
