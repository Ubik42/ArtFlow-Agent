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
    raise RuntimeError(f"ArtFlow modular environment failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m47-s1-modular-environment"
request = json.loads((evidence / "modular-environment-request.json").read_text(encoding="utf-8"))
zones = json.loads((evidence / "comfy-module-zone-receipt.json").read_text(encoding="utf-8"))
blender = json.loads((evidence / "blender-modular-environment-receipt.json").read_text(encoding="utf-8"))
manifest_path = evidence / next(item["relative_path"] for item in blender["artifacts"] if item["kind"] == "manifest")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if zones["request_sha256"] != request["request_sha256"] or blender["request_sha256"] != request["request_sha256"]:
    fail("receipt chain differs from the request")
for item in blender["artifacts"]:
    if sha256(evidence / item["relative_path"]) != item["sha256"]:
        fail(f"Blender artifact identity drifted: {item['relative_path']}")
project = Path(unreal.Paths.project_dir()).resolve()
source_file = project / "Content" / (request["source_candidate_scene_path"].removeprefix("/Game/") + ".umap")
source_before = sha256(source_file)
if source_before != request["source_candidate_sha256"]:
    fail("source candidate changed after request compilation")
identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Blender/Modular/M_{identity}"
meshes = {}
assets_reconciled = True
for variant in blender["variants"]:
    mesh = None
    for path in unreal.EditorAssetLibrary.list_assets(destination, recursive=True, include_folder=False):
        candidate = unreal.EditorAssetLibrary.load_asset(path)
        if (isinstance(candidate, unreal.StaticMesh)
                and unreal.EditorAssetLibrary.get_metadata_tag(candidate, "ArtFlow.ModularRequestSha256") == request["request_sha256"]
                and unreal.EditorAssetLibrary.get_metadata_tag(candidate, "ArtFlow.ModuleId") == variant["module_id"]):
            mesh = candidate
            break
    if mesh is None:
        assets_reconciled = False
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(evidence / variant["glb"]))
        task.set_editor_property("destination_path", destination)
        task.set_editor_property("destination_name", variant["object_name"])
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", False)
        task.set_editor_property("save", True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        mesh = next((unreal.EditorAssetLibrary.load_asset(path) for path in task.get_editor_property("imported_object_paths")
                     if isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.StaticMesh)), None)
    if not isinstance(mesh, unreal.StaticMesh):
        fail(f"Interchange did not produce module {variant['module_id']}")
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.ModularRequestSha256", request["request_sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.ModuleId", variant["module_id"])
    if unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh) == 0:
        unreal.EditorStaticMeshLibrary.add_simple_collisions(mesh, unreal.ScriptingCollisionShapeType.BOX)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
    meshes[variant["module_id"]] = mesh

candidate_name = f"Modular_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(request["source_candidate_scene_path"], candidate_package)
    if candidate is None:
        fail("could not derive modular environment candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
created = 0
placements = []
for item in manifest["placements"]:
    label = f"ArtFlow_Module_{item['placement_id']}"
    actor = next((value for value in actors if value.get_actor_label() == label), None)
    location = unreal.Vector(*item["location_cm"])
    rotation = unreal.Rotator(0, item["yaw_deg"], 0)
    if actor is None:
        actor = subsystem.spawn_actor_from_object(meshes[item["module_id"]], location, rotation)
        actor.set_actor_label(label)
        created += 1
    actor.tags = ["ArtFlow.Modular", request["request_id"], item["module_id"], item["placement_id"]]
    placements.append({"placement_id": item["placement_id"], "actor_label": label,
                       "module_id": item["module_id"], "mesh_path": meshes[item["module_id"]].get_path_name()})
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
screenshot = evidence / "unreal-modular-environment-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
camera = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_Camera"), None)
state = {"ticks": 0, "callback": None}


def finish():
    unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
    source_after = sha256(source_file)
    if source_after != source_before:
        fail("modular route changed the upstream foliage candidate")
    labels = {actor.get_actor_label() for actor in subsystem.get_all_level_actors()}
    if not all(item["actor_label"] in labels for item in placements):
        fail("not every registered module actor exists")
    result = {"schema_id": "artflow-unreal-modular-environment-receipt/1", "request_sha256": request["request_sha256"],
              "zone_receipt_sha256": zones["receipt_sha256"], "blender_receipt_sha256": blender["receipt_sha256"],
              "status": "reconciled" if assets_reconciled and candidate_reconciled and created == 0 else "generated",
              "engine_version": unreal.SystemLibrary.get_engine_version(), "source_candidate_scene_path": request["source_candidate_scene_path"],
              "candidate_scene_path": candidate_package, "mesh_paths": {key: value.get_path_name() for key, value in meshes.items()},
              "module_actor_count": len(placements), "created_actor_count": created, "duplicate_side_effect_count": 0,
              "placements": placements, "source_candidate_sha256_before": source_before, "source_candidate_sha256_after": source_after,
              "screenshot_path": screenshot.name, "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
              "capture_status": "captured" if screenshot.is_file() else "unavailable",
              "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-modular-environment-receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    unreal.log(f"ARTFLOW_MODULAR_RETURN status={result['status']} actors={len(placements)}")
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta):
    state["ticks"] += 1
    if state["ticks"] == 2 and isinstance(camera, unreal.CameraActor):
        unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(screenshot), camera, False, False)
    if screenshot.is_file() or state["ticks"] > 240:
        finish()


state["callback"] = unreal.register_slate_post_tick_callback(on_tick)
