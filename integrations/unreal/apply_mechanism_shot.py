from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import unreal


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow mechanism shot failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m53-s1-mechanism-shot"
request = json.loads((evidence / "mechanism-shot-request.json").read_text(encoding="utf-8"))
unsigned = dict(request)
unsigned.pop("request_sha256")
if canonical(unsigned) != request["request_sha256"]:
    fail("request fingerprint changed")
m51_root = repo / "artifacts/goal/m51-s1-mechanism-rig"
m51_receipt = json.loads(
    (m51_root / "unreal-mechanism-rig-receipt.json").read_text(encoding="utf-8")
)
if m51_receipt["receipt_sha256"] != request["mechanism_unreal_receipt_sha256"]:
    fail("registered M51 Unreal receipt changed")

project = Path(unreal.Paths.project_dir()).resolve()
content = project / "Content"


def asset_file(object_path: str) -> Path:
    package = object_path.split(".", 1)[0].removeprefix("/Game/")
    return content / f"{package}.uasset"


source_package = request["source_candidate_scene_path"]
source_file = content / (source_package.removeprefix("/Game/") + ".umap")
if sha256(source_file) != request["source_candidate_sha256"]:
    fail("source mechanism candidate identity changed")
source_before = sha256(source_file)
for name in ("skeletal_mesh", "skeleton", "animation"):
    path = asset_file(request[f"{name}_path"])
    if not path.is_file() or sha256(path) != request[f"{name}_sha256"]:
        fail(f"registered {name} asset identity changed")

mesh = unreal.EditorAssetLibrary.load_asset(request["skeletal_mesh_path"])
skeleton = unreal.EditorAssetLibrary.load_asset(request["skeleton_path"])
animation = unreal.EditorAssetLibrary.load_asset(request["animation_path"])
if not isinstance(mesh, unreal.SkeletalMesh):
    fail("registered skeletal mesh cannot be loaded")
if not isinstance(skeleton, unreal.Skeleton):
    fail("registered skeleton cannot be loaded")
if not isinstance(animation, unreal.AnimSequence):
    fail("registered animation cannot be loaded")

candidate_package = request["candidate_scene_path"]
candidate_name = candidate_package.rsplit("/", 1)[-1]
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(source_package, candidate_package)
    if candidate is None:
        fail("could not derive the mechanism-shot candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load the mechanism-shot candidate")
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsystem.get_all_level_actors()
mechanism = next(
    (actor for actor in actors if actor.get_actor_label() == "ArtFlow_Mechanism_ArticulatedGate"),
    None,
)
if not isinstance(mechanism, unreal.SkeletalMeshActor):
    fail("registered mechanism actor is unavailable")
component = mechanism.get_editor_property("skeletal_mesh_component")
if component.get_editor_property("skeletal_mesh_asset") != mesh:
    fail("mechanism actor references another skeletal mesh")
component.set_editor_property("pause_anims", False)

created_actors = 0
camera_label = "ArtFlow_MechanismShot_Camera"
camera = next((actor for actor in actors if actor.get_actor_label() == camera_label), None)
camera_reconciled = isinstance(camera, unreal.CineCameraActor)
if camera is None:
    camera = actor_subsystem.spawn_actor_from_class(
        unreal.CineCameraActor,
        unreal.Vector(*request["camera_location_cm"]),
        unreal.Rotator(roll=0, pitch=0, yaw=0),
    )
    created_actors += 1
if not isinstance(camera, unreal.CineCameraActor):
    fail("registered shot camera is not a CineCameraActor")
camera.set_actor_label(camera_label)
camera.set_actor_location(unreal.Vector(*request["camera_location_cm"]), False, False)
camera.set_actor_rotation(
    unreal.MathLibrary.find_look_at_rotation(
        unreal.Vector(*request["camera_location_cm"]),
        unreal.Vector(*request["camera_target_cm"]),
    ),
    False,
)
camera.get_cine_camera_component().set_editor_property(
    "current_focal_length", request["camera_focal_length_mm"]
)
camera.tags = ["ArtFlow.MechanismShot", request["request_id"], "Camera"]

light_label = "ArtFlow_MechanismShot_Cue"
light = next((actor for actor in actors if actor.get_actor_label() == light_label), None)
light_reconciled = isinstance(light, unreal.PointLight)
if light is None:
    light = actor_subsystem.spawn_actor_from_class(
        unreal.PointLight,
        unreal.Vector(2500, -180, 470),
        unreal.Rotator(roll=0, pitch=0, yaw=0),
    )
    created_actors += 1
if not isinstance(light, unreal.PointLight):
    fail("registered mechanism cue light is not a PointLight")
light.set_actor_label(light_label)
light_component = light.get_editor_property("point_light_component")
light_component.set_editor_property("intensity", request["cue_light_intensity"])
light_component.set_editor_property("use_temperature", True)
light_component.set_editor_property("temperature", request["cue_light_temperature_kelvin"])
light_component.set_editor_property("attenuation_radius", 1100.0)
light.tags = ["ArtFlow.MechanismShot", request["request_id"], "CueLight"]

sequence_object = request["sequence_asset_path"]
sequence_package, sequence_name = sequence_object.rsplit(".", 1)
sequence_reconciled = unreal.EditorAssetLibrary.does_asset_exist(sequence_object)
if sequence_reconciled:
    sequence = unreal.EditorAssetLibrary.load_asset(sequence_object)
else:
    sequence = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        sequence_name,
        sequence_package.rsplit("/", 1)[0],
        unreal.LevelSequence,
        unreal.LevelSequenceFactoryNew(),
    )
if not isinstance(sequence, unreal.LevelSequence):
    fail("could not create the registered mechanism Level Sequence")
recorded = unreal.EditorAssetLibrary.get_metadata_tag(
    sequence, "ArtFlow.MechanismShotRequestSha256"
)
if recorded not in {"", request["request_sha256"]}:
    fail("existing Level Sequence belongs to another mechanism shot")
configured = recorded == request["request_sha256"]
if not configured:
    sequence.set_display_rate(unreal.FrameRate(request["display_rate_fps"], 1))
    sequence.set_playback_start(request["playback_start_frame"])
    sequence.set_playback_end(request["playback_end_frame"])
    mechanism_binding = sequence.add_possessable(component)
    mechanism_binding.set_display_name("ArtFlow_Mechanism_Component")
    animation_track = mechanism_binding.add_track(unreal.MovieSceneSkeletalAnimationTrack)
    animation_section = animation_track.add_section()
    animation_section.set_range(
        request["playback_start_frame"], request["playback_end_frame"]
    )
    animation_section.params.animation = animation
    if request["camera_binding_mode"] != "spawnable":
        fail("mechanism shot camera binding mode changed")
    camera_binding = sequence.add_spawnable_from_instance(camera)
    camera_binding.set_display_name(camera_label)
    if request["camera_transform_track"] != "constant":
        fail("mechanism shot camera transform recipe changed")
    camera_transform_track = camera_binding.add_track(unreal.MovieScene3DTransformTrack)
    camera_transform_section = camera_transform_track.add_section()
    camera_transform_section.set_range(
        request["playback_start_frame"], request["playback_end_frame"]
    )
    camera_rotation = camera.get_actor_rotation()
    camera_values = {
        "Location.X": request["camera_location_cm"][0],
        "Location.Y": request["camera_location_cm"][1],
        "Location.Z": request["camera_location_cm"][2],
        "Rotation.X": camera_rotation.roll,
        "Rotation.Y": camera_rotation.pitch,
        "Rotation.Z": camera_rotation.yaw,
        "Scale.X": 1.0,
        "Scale.Y": 1.0,
        "Scale.Z": 1.0,
    }
    for channel in camera_transform_section.get_all_channels():
        channel.add_key(
            unreal.FrameNumber(request["playback_start_frame"]),
            float(camera_values[str(channel.channel_name)]),
        )
    light_binding = sequence.add_possessable(light)
    light_binding.set_display_name(light_label)
    camera_cut_track = sequence.add_track(unreal.MovieSceneCameraCutTrack)
    camera_cut = camera_cut_track.add_section()
    camera_cut.set_range(request["playback_start_frame"], request["playback_end_frame"])
    if request["camera_cut_binding_space"] != "sequence_local":
        fail("mechanism shot camera-cut binding space changed")
    camera_cut.set_camera_binding_id(sequence.get_binding_id(camera_binding))
    unreal.EditorAssetLibrary.set_metadata_tag(
        sequence, "ArtFlow.MechanismShotRequestSha256", request["request_sha256"]
    )
    unreal.EditorAssetLibrary.set_metadata_tag(
        sequence, "ArtFlow.SourceMechanismCandidateSha256", request["source_candidate_sha256"]
    )
    unreal.EditorAssetLibrary.save_loaded_asset(sequence, only_if_is_dirty=False)

bindings = sequence.get_bindings()
mechanism_bindings = [
    binding
    for binding in bindings
    if str(binding.get_display_name()) == "ArtFlow_Mechanism_Component"
]
camera_bindings = [
    binding for binding in bindings if str(binding.get_display_name()) == camera_label
]
light_bindings = [binding for binding in bindings if str(binding.get_display_name()) == light_label]
if len(mechanism_bindings) != 1 or len(camera_bindings) != 1 or len(light_bindings) != 1:
    fail("mechanism shot binding topology changed")
animation_tracks = [
    track
    for track in mechanism_bindings[0].get_tracks()
    if isinstance(track, unreal.MovieSceneSkeletalAnimationTrack)
]
if len(animation_tracks) != 1 or len(animation_tracks[0].get_sections()) != 1:
    fail("mechanism animation track topology changed")
camera_cut_count = sum(
    isinstance(track, unreal.MovieSceneCameraCutTrack) for track in sequence.get_tracks()
)
if camera_cut_count != 1:
    fail("mechanism shot camera-cut topology changed")
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

preview_paths = {
    item["label"]: evidence / f"unreal-mechanism-shot-{item['label']}.png"
    for item in request["frames"]
}
for path in preview_paths.values():
    if path.is_file():
        path.unlink()
movie_dir = evidence / "sequence-frames"
if movie_dir.is_dir():
    shutil.rmtree(movie_dir)
movie_dir.mkdir(parents=True)


def finish(success: bool) -> None:
    if not success:
        unreal.log_error("ARTFLOW_MECHANISM_SHOT_FAILED sequence render failed")
        unreal.SystemLibrary.quit_editor()
        return
    rendered = sorted(movie_dir.glob("*.png"))
    by_frame = {
        int(path.stem.rsplit("_", 1)[-1]): path
        for path in rendered
        if path.stem.rsplit("_", 1)[-1].isdigit()
    }
    for item in request["frames"]:
        source = by_frame.get(item["frame"])
        if source is None:
            fail(f"sequence render omitted frame {item['frame']}")
        shutil.copy2(source, preview_paths[item["label"]])
    unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
    source_after = sha256(source_file)
    if source_after != source_before:
        fail("mechanism shot changed the source candidate")
    sequence_file = asset_file(sequence_object)
    result = {
        "schema_id": "artflow-unreal-mechanism-shot-receipt/1",
        "request_sha256": request["request_sha256"],
        "mechanism_unreal_receipt_sha256": m51_receipt["receipt_sha256"],
        "status": "reconciled"
        if candidate_reconciled
        and sequence_reconciled
        and configured
        and camera_reconciled
        and light_reconciled
        and created_actors == 0
        else "created",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "source_candidate_scene_path": source_package,
        "source_candidate_sha256_before": source_before,
        "source_candidate_sha256_after": source_after,
        "candidate_scene_path": candidate_package,
        "sequence_asset_path": sequence.get_path_name(),
        "sequence_sha256": sha256(sequence_file),
        "sequence_binding_count": len(bindings),
        "mechanism_binding_count": len(mechanism_bindings),
        "animation_track_count": len(animation_tracks),
        "animation_section_count": len(animation_tracks[0].get_sections()),
        "camera_binding_count": len(camera_bindings),
        "light_binding_count": len(light_bindings),
        "camera_cut_track_count": camera_cut_count,
        "created_actor_count": created_actors,
        "created_package_count": int(not candidate_reconciled) + int(not sequence_reconciled),
        "created_binding_count": 0 if configured else len(bindings),
        "created_track_count": 0 if configured else 3,
        "duplicate_track_count": 0,
        "frame_numbers": [item["frame"] for item in request["frames"]],
        "preview_capture_mode": "sequencer_render_movie",
        "preview_paths": {key: path.name for key, path in preview_paths.items()},
        "preview_sha256s": {key: sha256(path) for key, path in preview_paths.items()},
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-mechanism-shot-receipt.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    unreal.log(
        f"ARTFLOW_MECHANISM_SHOT status={result['status']} bindings={len(bindings)} frames=3"
    )
    unreal.SystemLibrary.quit_editor()


capture = unreal.AutomatedLevelSequenceCapture()
capture.settings.output_directory = unreal.DirectoryPath(str(movie_dir))
capture.settings.output_format = "AF_Mechanism_{frame}"
capture.settings.overwrite_existing = True
capture.settings.use_relative_frame_numbers = False
capture.settings.zero_pad_frame_numbers = 4
capture.settings.use_custom_frame_rate = True
capture.settings.custom_frame_rate = unreal.FrameRate(request["display_rate_fps"], 1)
capture.settings.resolution.res_x = 1280
capture.settings.resolution.res_y = 720
capture.settings.cinematic_mode = True
capture.settings.allow_movement = False
capture.settings.allow_turning = False
capture.settings.show_player = False
capture.settings.show_hud = False
capture.settings.enable_texture_streaming = False
capture.use_separate_process = False
capture.use_custom_start_frame = True
capture.use_custom_end_frame = True
capture.custom_start_frame = unreal.FrameNumber(request["playback_start_frame"])
capture.custom_end_frame = unreal.FrameNumber(request["playback_end_frame"])
capture.level_sequence_asset = unreal.SoftObjectPath(sequence.get_path_name())
capture.set_image_capture_protocol_type(
    unreal.load_class(None, "/Script/MovieSceneCapture.ImageSequenceProtocol_PNG")
)
render_finished = unreal.OnRenderMovieStopped()
render_finished.bind_callable(finish)
unreal.SequencerTools.render_movie(capture, render_finished)
unreal.log("ARTFLOW_MECHANISM_SHOT_PENDING rendering the registered Level Sequence")
