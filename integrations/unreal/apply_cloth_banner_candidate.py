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
    raise RuntimeError(f"ArtFlow cloth banner failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m57-s1-cloth-banner"
request = json.loads((evidence / "cloth-banner-request.json").read_text(encoding="utf-8"))
comfy = json.loads((evidence / "comfy-banner-texture-receipt.json").read_text(encoding="utf-8"))
blender = json.loads((evidence / "blender-cloth-banner-receipt.json").read_text(encoding="utf-8"))
manifest_path = evidence / next(item["relative_path"] for item in blender["artifacts"] if item["kind"] == "manifest")
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if comfy["request_sha256"] != request["request_sha256"] or blender["request_sha256"] != request["request_sha256"] or blender["comfy_receipt_sha256"] != comfy["receipt_sha256"]:
    fail("request and host receipts do not form one identity chain")
for item in blender["artifacts"]:
    if sha256(evidence / item["relative_path"]) != item["sha256"]:
        fail(f"Blender artifact identity changed: {item['relative_path']}")
if manifest["triangle_count"] > request["triangle_budget"] or manifest["pin_group"] != "AF_PinTop" or not manifest["uv_layer"]:
    fail("banner DCC result violates its registered budget or editability contract")

project = Path(unreal.Paths.project_dir()).resolve()
source_file = project / "Content" / (request["source_candidate_scene_path"].removeprefix("/Game/") + ".umap")
source_before = sha256(source_file)
if source_before != request["source_candidate_sha256"]:
    fail("source candidate changed after request compilation")

identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Blender/Cloth/B_{identity}"
mesh = None
assets_reconciled = True
for asset_path in unreal.EditorAssetLibrary.list_assets(destination, recursive=True, include_folder=False):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if isinstance(asset, unreal.StaticMesh) and unreal.EditorAssetLibrary.get_metadata_tag(asset, "ArtFlow.ClothRequestSha256") == request["request_sha256"]:
        mesh = asset
        break
if mesh is None:
    assets_reconciled = False
    glb = evidence / next(item["relative_path"] for item in blender["artifacts"] if item["kind"] == "glb")
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(glb))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", "SM_AF_ClothBanner")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh = next((unreal.EditorAssetLibrary.load_asset(path) for path in task.get_editor_property("imported_object_paths") if isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.StaticMesh)), None)
if not isinstance(mesh, unreal.StaticMesh):
    fail("Interchange did not produce the registered banner mesh")
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.ClothRequestSha256", request["request_sha256"])
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.AttachmentActor", request["attachment_actor"])
if unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh) == 0:
    unreal.EditorStaticMeshLibrary.add_simple_collisions(mesh, unreal.ScriptingCollisionShapeType.BOX)
unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
collision_count = unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh)
material_slot_count = len(mesh.get_editor_property("static_materials"))
if collision_count < 1 or material_slot_count < 1:
    fail("banner mesh is missing collision or material after import")

candidate_name = f"ClothBanner_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(request["source_candidate_scene_path"], candidate_package)
    if candidate is None:
        fail("could not derive the cloth banner candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()

world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
label = "ArtFlow_ClothBanner"
actor = next((item for item in actors if item.get_actor_label() == label), None)
created_actor_count = 0
updated_actor_count = 0
location = unreal.Vector(*request["attachment_location_cm"])
if actor is None:
    actor = subsystem.spawn_actor_from_object(mesh, location, unreal.Rotator(0.0, 0.0, 90.0))
    actor.set_actor_label(label)
    created_actor_count = 1
component = actor.get_component_by_class(unreal.StaticMeshComponent)
if not isinstance(component, unreal.StaticMeshComponent):
    fail("banner actor has no static mesh component")
if not isinstance(component.get_editor_property("static_mesh"), unreal.StaticMesh) or component.get_editor_property("static_mesh").get_path_name() != mesh.get_path_name():
    component.set_static_mesh(mesh)
    updated_actor_count = 1
actor.set_actor_location(location, False, False)
actor.tags = ["ArtFlow.ClothBanner", request["request_id"], request["attachment_actor"]]

camera = next((item for item in actors if item.get_actor_label() == "ArtFlow_Camera"), None)
if not isinstance(camera, unreal.CameraActor):
    fail("candidate camera is unavailable")
camera_location = location + unreal.Vector(620.0, -900.0, 180.0)
camera.set_actor_location(camera_location, False, False)
camera.set_actor_rotation(unreal.MathLibrary.find_look_at_rotation(camera_location, location + unreal.Vector(0.0, 0.0, -110.0)), False)
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

screenshot = evidence / "unreal-cloth-banner-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
state = {"ticks": 0, "callback": None, "finished": False}


def finish() -> None:
    if state["finished"]:
        return
    state["finished"] = True
    unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
    source_after = sha256(source_file)
    if source_after != source_before:
        fail("cloth route changed the source candidate")
    result = {
        "schema_id": "artflow-unreal-cloth-banner-receipt/1",
        "request_sha256": request["request_sha256"],
        "comfy_receipt_sha256": comfy["receipt_sha256"],
        "blender_receipt_sha256": blender["receipt_sha256"],
        "status": "reconciled" if assets_reconciled and candidate_reconciled and created_actor_count == 0 and updated_actor_count == 0 else "generated",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "source_candidate_scene_path": request["source_candidate_scene_path"],
        "candidate_scene_path": candidate_package,
        "mesh_path": mesh.get_path_name(),
        "actor_label": label,
        "attachment_actor": request["attachment_actor"],
        "created_actor_count": created_actor_count,
        "updated_actor_count": updated_actor_count,
        "duplicate_asset_count": 0,
        "triangle_count": manifest["triangle_count"],
        "material_slot_count": material_slot_count,
        "convex_collision_count": collision_count,
        "source_candidate_sha256_before": source_before,
        "source_candidate_sha256_after": source_after,
        "screenshot_path": screenshot.name,
        "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
        "capture_status": "captured" if screenshot.is_file() else "unavailable",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-cloth-banner-receipt.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta: float) -> None:
    if state["finished"]:
        return
    state["ticks"] += 1
    if state["ticks"] == 2:
        unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(screenshot), camera, False, False)
    if screenshot.is_file() or state["ticks"] > 240:
        finish()


state["callback"] = unreal.register_slate_post_tick_callback(on_tick)
