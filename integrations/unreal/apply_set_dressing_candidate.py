from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import unreal


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow set dressing return failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m28-s1-set-dressing"
surface_root = repo / "artifacts/goal/m26-s1-surface-bake"
request = json.loads((evidence / "set-dressing-request.json").read_text(encoding="utf-8"))
receipt = json.loads((evidence / "set-dressing-receipt.json").read_text(encoding="utf-8"))
surface_return = json.loads((surface_root / "unreal-surface-return-receipt.json").read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-blender-set-dressing-request/1" or receipt.get("request_sha256") != request.get("request_sha256"):
    fail("request and receipt identity mismatch")
if request["surface_receipt_sha256"] != json.loads((surface_root / "surface-receipt.json").read_text(encoding="utf-8"))["receipt_sha256"]:
    fail("surface receipt identity drifted")
prototype_artifact = next(item for item in receipt["artifacts"] if item["kind"] == "prototype_glb")
prototype_path = (evidence / prototype_artifact["relative_path"]).resolve()
if evidence.resolve() not in prototype_path.parents or sha256(prototype_path) != prototype_artifact["sha256"]:
    fail("prototype GLB identity mismatch")

project = Path(unreal.Paths.project_dir()).resolve()
source_map = project / "Content/ArtFlowDemo.umap"
source_before = sha256(source_map)
if source_before != request["source_level_sha256"]:
    fail("source level changed after request compilation")
identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Blender/Dressing/D_{identity}"
mesh = None
for path in unreal.EditorAssetLibrary.list_assets(destination, recursive=True):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if isinstance(asset, unreal.StaticMesh) and unreal.EditorAssetLibrary.get_metadata_tag(asset, "ArtFlow.SetDressingRequestSha256") == request["request_sha256"]:
        mesh = asset
        break
mesh_reconciled = mesh is not None
if mesh is None:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(prototype_path))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", "SM_AF_Rubble_Prototype")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    for path in task.get_editor_property("imported_object_paths"):
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if isinstance(asset, unreal.StaticMesh):
            mesh = asset
            break
if not isinstance(mesh, unreal.StaticMesh):
    fail("Interchange did not produce the registered rubble mesh")
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.SetDressingRequestSha256", request["request_sha256"])
mesh_library = unreal.EditorStaticMeshLibrary
if mesh_library.get_convex_collision_count(mesh) == 0:
    mesh_library.add_simple_collisions(mesh, unreal.ScriptingCollisionShapeType.NDOP10_X)
unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)

candidate_name = f"Dressing_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    world_asset = unreal.EditorAssetLibrary.duplicate_asset(surface_return["candidate_scene_path"], candidate_package)
    if world_asset is None:
        fail("could not duplicate the registered surface candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(world_asset, only_if_is_dirty=False)
    del world_asset
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load set-dressing candidate")
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
surface_actor = next((item for item in actors if item.get_actor_label() == surface_return["actor_label"]), None)
if not isinstance(surface_actor, unreal.StaticMeshActor):
    fail("surface anchor actor is missing")
offset = surface_actor.get_actor_location()
material = unreal.EditorAssetLibrary.load_asset(surface_return["imported_material_paths"][0])
created = 0
for transform in receipt["transforms"]:
    label = f"ArtFlow_Settled_{transform['instance_id']}"
    actor = next((item for item in actors if item.get_actor_label() == label), None)
    if actor is None:
        loc = transform["location_m"]
        actor = subsystem.spawn_actor_from_object(mesh, unreal.Vector(offset.x + loc[0] * 100, offset.y - loc[1] * 100, offset.z + loc[2] * 100), unreal.Rotator())
        created += 1
    actor.set_actor_label(label)
    rotation = transform["rotation_deg"]
    actor.set_actor_rotation(unreal.Rotator(pitch=rotation[0], yaw=-rotation[2], roll=rotation[1]), False)
    actor.set_actor_scale3d(unreal.Vector(*transform["scale"]))
    component = actor.get_editor_property("static_mesh_component")
    component.set_material(0, material)
    actor.tags = ["ArtFlow.SetDressing", request["request_id"], transform["instance_id"]]
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

camera = next((item for item in actors if item.get_actor_label() == "ArtFlow_Camera"), None)
if not isinstance(camera, unreal.CameraActor):
    fail("registered camera is missing")
screenshot = evidence / "unreal-set-dressing-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(screenshot), camera, False, False)
source_after = sha256(source_map)
if source_after != source_before:
    fail("source level changed during set-dressing return")
result = {
    "schema_id": "artflow-unreal-set-dressing-return-receipt/1",
    "request_id": request["request_id"], "request_sha256": request["request_sha256"],
    "blender_set_dressing_receipt_sha256": receipt["receipt_sha256"],
    "status": "reconciled" if mesh_reconciled and candidate_reconciled and created == 0 else "imported",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "source_candidate_scene_path": surface_return["candidate_scene_path"],
    "candidate_scene_path": candidate_package, "static_mesh_path": mesh.get_path_name(),
    "instance_count": len(receipt["transforms"]), "created_actor_count": created,
    "simple_collision_count": mesh_library.get_convex_collision_count(mesh),
    "source_level_sha256_before": source_before, "source_level_sha256_after": source_after,
    "screenshot_path": screenshot.name, "screenshot_sha256": None, "capture_status": "requested",
    "duplicate_side_effect_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical(result)
(evidence / "unreal-set-dressing-return-receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
unreal.log(f"ARTFLOW_SET_DRESSING_RETURN_SUBMITTED status={result['status']} candidate={candidate_package}")
