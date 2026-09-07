from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import unreal


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow simulation cache failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m43-s1-simulation-cache"
request_path = evidence / "simulation-cache-request.json"
receipt_path = evidence / "blender-simulation-cache-receipt.json"
request = json.loads(request_path.read_text(encoding="utf-8"))
receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
if receipt["request_sha256"] != request["request_sha256"]:
    fail("Blender cache belongs to another request")
cache_item = next(item for item in receipt["artifacts"] if item["kind"] == "alembic")
cache_file = evidence / cache_item["relative_path"]
if sha256(cache_file) != cache_item["sha256"] or cache_file.stat().st_size > request["max_cache_bytes"]:
    fail("Alembic identity or size budget changed")

project = Path(unreal.Paths.project_dir()).resolve()
content = project / "Content"
source_candidate = request["source_candidate_scene_path"]
source_candidate_file = content / (source_candidate.removeprefix("/Game/") + ".umap")
if sha256(source_candidate_file) != request["source_candidate_sha256"]:
    fail("terrain candidate identity changed")
source_before = sha256(source_candidate_file)
identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Caches/SC_{identity}"
cache_object = f"{destination}/GC_AF_WindVeil.GC_AF_WindVeil"
cache_existed = unreal.EditorAssetLibrary.does_asset_exist(cache_object)
if cache_existed:
    geometry_cache = unreal.EditorAssetLibrary.load_asset(cache_object)
else:
    settings = unreal.AbcImportSettings()
    settings.set_editor_property("import_type", unreal.AlembicImportType.GEOMETRY_CACHE)
    sampling = settings.get_editor_property("sampling_settings")
    sampling.set_editor_property("frame_start", request["frame_start"])
    sampling.set_editor_property("frame_end", request["frame_end"])
    settings.set_editor_property("sampling_settings", sampling)
    factory = unreal.AlembicImportFactory()
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(cache_file))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", "GC_AF_WindVeil")
    task.set_editor_property("factory", factory)
    task.set_editor_property("options", settings)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    geometry_cache = unreal.EditorAssetLibrary.load_asset(cache_object)
if not isinstance(geometry_cache, unreal.GeometryCache):
    fail("Alembic did not import as Geometry Cache")
unreal.EditorAssetLibrary.set_metadata_tag(geometry_cache, "ArtFlow.SimulationRequestSha256", request["request_sha256"])
unreal.EditorAssetLibrary.set_metadata_tag(geometry_cache, "ArtFlow.AlembicSha256", cache_item["sha256"])
unreal.EditorAssetLibrary.save_loaded_asset(geometry_cache, only_if_is_dirty=False)

candidate_name = f"Simulation_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_existed = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_existed:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(source_candidate, candidate_package)
    if candidate is None:
        fail("could not derive simulation candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
cache_actor = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_WindVeil_Cache"), None)
actor_existed = cache_actor is not None
if cache_actor is None:
    cache_actor = subsystem.spawn_actor_from_class(unreal.GeometryCacheActor, unreal.Vector(0, 180, 80))
    cache_actor.set_actor_label("ArtFlow_WindVeil_Cache")
cache_actor.set_actor_location(unreal.Vector(300, 300, 80), False, False)
cache_actor.set_actor_scale3d(unreal.Vector(70, 70, 70))
cache_actor.set_actor_rotation(unreal.Rotator(0, 0, 0), False)
component = cache_actor.get_geometry_cache_component()
component.set_geometry_cache(geometry_cache)
lookdev_material = unreal.EditorAssetLibrary.load_asset(
    "/Game/ArtFlow/Generated/Materials/MV_1a77d442c379/MI_AF_Wayfinder_A_SceneVariant"
)
if isinstance(lookdev_material, unreal.MaterialInterface):
    component.set_material(0, lookdev_material)
component.set_editor_property("looping", True)
component.set_editor_property("playback_speed", 1.0)

sequence_object = request["sequence_asset_path"]
sequence_package, sequence_name = sequence_object.rsplit(".", 1)
sequence_existed = unreal.EditorAssetLibrary.does_asset_exist(sequence_object)
sequence = unreal.EditorAssetLibrary.load_asset(sequence_object) if sequence_existed else unreal.AssetToolsHelpers.get_asset_tools().create_asset(sequence_name, sequence_package.rsplit("/", 1)[0], unreal.LevelSequence, unreal.LevelSequenceFactoryNew())
if not isinstance(sequence, unreal.LevelSequence):
    fail("could not create simulation Level Sequence")
configured = unreal.EditorAssetLibrary.get_metadata_tag(sequence, "ArtFlow.SimulationRequestSha256") == request["request_sha256"]
if not configured:
    sequence.set_display_rate(unreal.FrameRate(request["frame_rate"], 1))
    sequence.set_playback_start(request["frame_start"])
    sequence.set_playback_end(request["frame_end"] + 1)
    binding = sequence.add_possessable(component)
    binding.set_display_name("ArtFlow Wind Veil Cache")
    track = binding.add_track(unreal.MovieSceneGeometryCacheTrack)
    section = track.add_section()
    section.set_range(request["frame_start"], request["frame_end"] + 1)
    params = section.get_editor_property("params")
    params.set_editor_property("geometry_cache_asset", geometry_cache)
    params.set_editor_property("play_rate", 1.0)
    section.set_editor_property("params", params)
    unreal.EditorAssetLibrary.set_metadata_tag(sequence, "ArtFlow.SimulationRequestSha256", request["request_sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(sequence, "ArtFlow.AlembicSha256", cache_item["sha256"])
    unreal.EditorAssetLibrary.save_loaded_asset(sequence, only_if_is_dirty=False)

bindings = sequence.get_bindings()
cache_bindings = [binding for binding in bindings if str(binding.get_display_name()) == "ArtFlow Wind Veil Cache"]
if len(cache_bindings) != 1:
    fail(f"expected one cache binding, got {len(cache_bindings)}")
tracks = [track for track in cache_bindings[0].get_tracks() if isinstance(track, unreal.MovieSceneGeometryCacheTrack)]
if len(tracks) != 1 or len(tracks[0].get_sections()) != 1:
    fail("expected one Geometry Cache track and section")
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

screenshot = evidence / "unreal-simulation-cache-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
camera = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_Camera"), None)
state = {"ticks": 0, "callback": None}


def finish() -> None:
    source_after = sha256(source_candidate_file)
    if source_after != source_before:
        fail("simulation return changed the terrain candidate")
    sequence_file = content / (sequence_package.removeprefix("/Game/") + ".uasset")
    result = {"schema_id": "artflow-unreal-simulation-cache-receipt/1", "request_sha256": request["request_sha256"],
              "blender_receipt_sha256": receipt["receipt_sha256"],
              "status": "reconciled" if cache_existed and candidate_existed and actor_existed and sequence_existed and configured else "created",
              "engine_version": unreal.SystemLibrary.get_engine_version(), "geometry_cache_path": geometry_cache.get_path_name(),
              "candidate_scene_path": candidate_package, "source_candidate_scene_path": source_candidate,
              "source_candidate_sha256_before": source_before, "source_candidate_sha256_after": source_after,
              "sequence_asset_path": sequence.get_path_name(), "sequence_sha256": sha256(sequence_file),
              "cache_binding_count": len(cache_bindings), "geometry_cache_track_count": len(tracks),
              "geometry_cache_section_count": len(tracks[0].get_sections()), "frame_range": [request["frame_start"], request["frame_end"]],
              "duplicate_asset_count": 0, "screenshot_path": screenshot.name,
              "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
              "capture_status": "captured" if screenshot.is_file() else "unavailable",
              "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-simulation-cache-receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    unreal.log(f"ARTFLOW_SIMULATION_CACHE status={result['status']} sequence={sequence.get_path_name()}")
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta: float) -> None:
    state["ticks"] += 1
    if screenshot.is_file() or state["ticks"] > 240:
        finish()


if isinstance(camera, unreal.CameraActor):
    unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(screenshot), camera, False, False)
    state["callback"] = unreal.register_slate_post_tick_callback(on_tick)
else:
    finish()
