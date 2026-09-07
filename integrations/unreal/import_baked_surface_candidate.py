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
    raise RuntimeError(f"ArtFlow surface return failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m26-s1-surface-bake"
lookdev = repo / "artifacts/goal/m24-s2-scene-lookdev"
request = json.loads((evidence / "surface-request.json").read_text(encoding="utf-8"))
receipt = json.loads((evidence / "surface-receipt.json").read_text(encoding="utf-8"))
lookdev_return = json.loads(
    (lookdev / "unreal-lookdev-return-receipt.json").read_text(encoding="utf-8")
)
if request.get("schema_id") != "artflow-blender-surface-request/1":
    fail("unsupported surface request")
if receipt.get("request_sha256") != request.get("request_sha256"):
    fail("surface receipt does not match the request")
if request["lookdev_receipt_sha256"] != sha256(lookdev / "lookdev-receipt.json"):
    fail("lookdev receipt identity drifted")
glb = next(item for item in receipt["artifacts"] if item["kind"] == "glb")
glb_path = (evidence / glb["relative_path"]).resolve()
if evidence.resolve() not in glb_path.parents or sha256(glb_path) != glb["sha256"]:
    fail("surface GLB identity mismatch")

project = Path(unreal.Paths.project_dir()).resolve()
source_map = project / "Content/ArtFlowDemo.umap"
source_before = sha256(source_map)
if source_before != request["source_level_sha256"]:
    fail("source level changed after the surface task was compiled")

identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Blender/Surface/S_{identity}"
mesh = None
for asset_path in unreal.EditorAssetLibrary.list_assets(destination, recursive=True):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if isinstance(asset, unreal.StaticMesh) and unreal.EditorAssetLibrary.get_metadata_tag(
        asset, "ArtFlow.SurfaceRequestSha256"
    ) == request["request_sha256"]:
        mesh = asset
        break
asset_reconciled = mesh is not None
imported_paths = []
if mesh is None:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(glb_path))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", "SM_AF_ShrineCourtyard_Baked")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported_paths = list(task.get_editor_property("imported_object_paths"))
    for path in imported_paths:
        asset = unreal.EditorAssetLibrary.load_asset(path)
        if isinstance(asset, unreal.StaticMesh):
            mesh = asset
            break
if not isinstance(mesh, unreal.StaticMesh):
    fail(f"Interchange did not produce a StaticMesh: {imported_paths}")
unreal.EditorAssetLibrary.set_metadata_tag(
    mesh, "ArtFlow.SurfaceRequestSha256", request["request_sha256"]
)
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.SourceGLBSha256", glb["sha256"])
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.Generator", request["capability_id"])
mesh_library = unreal.EditorStaticMeshLibrary
if mesh_library.get_convex_collision_count(mesh) == 0:
    mesh_library.add_simple_collisions(mesh, unreal.ScriptingCollisionShapeType.NDOP10_X)
unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)

candidate_name = f"Surface_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    world_asset = unreal.EditorAssetLibrary.duplicate_asset(
        lookdev_return["candidate_scene_path"], candidate_package
    )
    if world_asset is None:
        fail("could not duplicate the registered lookdev candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(world_asset, only_if_is_dirty=False)
    del world_asset
    unreal.SystemLibrary.collect_garbage()

world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load the isolated surface candidate")
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsystem.get_all_level_actors()
baked_label = "ArtFlow_Blender_ShrineCourtyard_Baked"
actor = next((item for item in actors if item.get_actor_label() == baked_label), None)
actor_reconciled = actor is not None
if actor is None:
    actor = next(
        (item for item in actors if item.get_actor_label() == lookdev_return["generated_actor_label"]),
        None,
    )
if not isinstance(actor, unreal.StaticMeshActor):
    fail("registered Blender scene actor is missing")
component = actor.get_editor_property("static_mesh_component")
component.set_static_mesh(mesh)
for slot in range(component.get_num_materials()):
    component.set_material(slot, mesh.get_material(slot))
actor.set_actor_label(baked_label)
actor.tags = ["ArtFlow.SurfaceBaked", request["request_id"], request["uv_set"]]
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

camera = next((item for item in actors if item.get_actor_label() == "ArtFlow_Camera"), None)
if not isinstance(camera, unreal.CameraActor):
    fail("registered camera is missing")
screenshot = evidence / "unreal-surface-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(screenshot), camera, False, False)

source_after = sha256(source_map)
if source_after != source_before:
    fail("source level changed while returning the surface candidate")
assets = unreal.EditorAssetLibrary.list_assets(destination, recursive=True)
materials = [path for path in assets if isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.MaterialInterface)]
textures = [path for path in assets if isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.Texture)]
uv_channels = mesh_library.get_num_uv_channels(mesh, 0)

result = {
    "schema_id": "artflow-unreal-surface-return-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "blender_surface_receipt_sha256": receipt["receipt_sha256"],
    "status": "reconciled" if asset_reconciled and candidate_reconciled and actor_reconciled else "imported",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "source_candidate_scene_path": lookdev_return["candidate_scene_path"],
    "candidate_scene_path": candidate_package,
    "static_mesh_path": mesh.get_path_name(),
    "actor_label": baked_label,
    "vertex_count": mesh_library.get_number_verts(mesh, 0),
    "triangle_count": mesh.get_num_triangles(0),
    "uv_channel_count": uv_channels,
    "material_slot_count": len(mesh.get_editor_property("static_materials")),
    "imported_material_paths": materials,
    "imported_texture_paths": textures,
    "simple_collision_count": mesh_library.get_convex_collision_count(mesh),
    "source_level_sha256_before": source_before,
    "source_level_sha256_after": source_after,
    "screenshot_path": screenshot.name,
    "screenshot_sha256": None,
    "capture_status": "requested",
    "duplicate_side_effect_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical(result)
(evidence / "unreal-surface-return-receipt.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
unreal.log(
    f"ARTFLOW_SURFACE_RETURN_SUBMITTED status={result['status']} candidate={candidate_package}"
)
