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
    raise RuntimeError(f"ArtFlow surface-detail return failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m30-s1-surface-detail"
surface_root = repo / "artifacts/goal/m26-s1-surface-bake"
dressing_root = repo / "artifacts/goal/m28-s1-set-dressing"
request = json.loads((evidence / "surface-detail-request.json").read_text(encoding="utf-8"))
comfy_receipt = json.loads(
    (evidence / "comfy-surface-detail-receipt.json").read_text(encoding="utf-8")
)
blender_receipt = json.loads(
    (evidence / "blender-surface-detail-receipt.json").read_text(encoding="utf-8")
)
dressing_return = json.loads(
    (dressing_root / "unreal-set-dressing-return-receipt.json").read_text(encoding="utf-8")
)
surface_return = json.loads(
    (surface_root / "unreal-surface-return-receipt.json").read_text(encoding="utf-8")
)
if request.get("schema_id") != "artflow-surface-detail-request/1":
    fail("unsupported request")
if comfy_receipt.get("request_sha256") != request.get("request_sha256"):
    fail("Comfy receipt identity mismatch")
if blender_receipt.get("request_sha256") != request.get("request_sha256"):
    fail("Blender receipt identity mismatch")
if blender_receipt.get("comfy_receipt_sha256") != comfy_receipt.get("receipt_sha256"):
    fail("Blender projection references another Comfy result")
if dressing_return.get("candidate_scene_path") != request.get("source_candidate_scene_path"):
    fail("source dressing candidate identity drifted")
glb_artifact = next(
    (item for item in blender_receipt["artifacts"] if item["kind"] == "glb"), None
)
if glb_artifact is None:
    fail("Blender projection GLB is missing")
glb_path = (evidence / glb_artifact["relative_path"]).resolve()
if evidence.resolve() not in glb_path.parents or sha256(glb_path) != glb_artifact["sha256"]:
    fail("Blender projection GLB identity drifted")

project = Path(unreal.Paths.project_dir()).resolve()
source_map = project / "Content/ArtFlowDemo.umap"
source_before = sha256(source_map)
if source_before != request["source_level_sha256"]:
    fail("source level changed after surface-detail compilation")

identity = request["request_sha256"][:12]
result_identity = blender_receipt["receipt_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Blender/Detail/D_{result_identity}"
mesh = None
for path in unreal.EditorAssetLibrary.list_assets(destination, recursive=True):
    asset = unreal.EditorAssetLibrary.load_asset(path)
    if (
        isinstance(asset, unreal.StaticMesh)
        and unreal.EditorAssetLibrary.get_metadata_tag(
            asset, "ArtFlow.SurfaceDetailRequestSha256"
        )
        == request["request_sha256"]
        and unreal.EditorAssetLibrary.get_metadata_tag(
            asset, "ArtFlow.BlenderSurfaceDetailReceiptSha256"
        )
        == blender_receipt["receipt_sha256"]
    ):
        mesh = asset
        break
asset_reconciled = mesh is not None
if mesh is None:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(glb_path))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", "SM_AF_Inlay_ProjectedDetail")
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
    fail("Interchange did not produce the projected-detail mesh")
unreal.EditorAssetLibrary.set_metadata_tag(
    mesh, "ArtFlow.SurfaceDetailRequestSha256", request["request_sha256"]
)
unreal.EditorAssetLibrary.set_metadata_tag(
    mesh, "ArtFlow.BlenderSurfaceDetailReceiptSha256", blender_receipt["receipt_sha256"]
)
unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)

destination_assets = unreal.EditorAssetLibrary.list_assets(destination, recursive=True)
projection_texture = next(
    (
        unreal.EditorAssetLibrary.load_asset(path)
        for path in destination_assets
        if "AF_Inlay_ProjectionTexture" in path
        and isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.Texture2D)
    ),
    None,
)
if not isinstance(projection_texture, unreal.Texture2D):
    fail("imported projection texture is missing")
engine_material_name = "M_AF_ProjectedInlay_Engine"
engine_material_object = f"{destination}/{engine_material_name}.{engine_material_name}"
engine_material = (
    unreal.EditorAssetLibrary.load_asset(engine_material_object)
    if unreal.EditorAssetLibrary.does_asset_exist(engine_material_object)
    else None
)
if engine_material is None:
    engine_material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        engine_material_name,
        destination,
        unreal.Material,
        unreal.MaterialFactoryNew(),
    )
    if not isinstance(engine_material, unreal.Material):
        fail("could not create the engine projection material")
    engine_material.set_editor_property("two_sided", True)
    sample = unreal.MaterialEditingLibrary.create_material_expression(
        engine_material, unreal.MaterialExpressionTextureSample, -320, 0
    )
    sample.set_editor_property("texture", projection_texture)
    for material_property in (
        unreal.MaterialProperty.MP_BASE_COLOR,
    ):
        if not unreal.MaterialEditingLibrary.connect_material_property(
            sample, "RGB", material_property
        ):
            fail("could not connect the projection texture to the engine material")
    emissive = unreal.MaterialEditingLibrary.create_material_expression(
        engine_material, unreal.MaterialExpressionConstant3Vector, -320, 180
    )
    emissive.set_editor_property(
        "constant", unreal.LinearColor(0.015, 0.42, 0.32, 1.0)
    )
    if not unreal.MaterialEditingLibrary.connect_material_property(
        emissive, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        fail("could not connect the projection emissive color")
    unreal.MaterialEditingLibrary.recompile_material(engine_material)
    unreal.EditorAssetLibrary.set_metadata_tag(
        engine_material,
        "ArtFlow.BlenderSurfaceDetailReceiptSha256",
        blender_receipt["receipt_sha256"],
    )
    unreal.EditorAssetLibrary.save_loaded_asset(engine_material, only_if_is_dirty=False)

candidate_name = f"Detail_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    world_asset = unreal.EditorAssetLibrary.duplicate_asset(
        dressing_return["candidate_scene_path"], candidate_package
    )
    if world_asset is None:
        fail("could not duplicate the registered dressing candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(world_asset, only_if_is_dirty=False)
    del world_asset
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load surface-detail candidate")
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def apply_projection() -> tuple[int, int]:
    actors = subsystem.get_all_level_actors()
    label = "ArtFlow_Projected_Inlay"
    anchor = next(
        (actor for actor in actors if actor.get_actor_label() == surface_return["actor_label"]),
        None,
    )
    if not isinstance(anchor, unreal.StaticMeshActor):
        fail("surface anchor actor is missing")
    anchor_location = anchor.get_actor_location()
    anchor_rotation = anchor.get_actor_rotation()
    anchor_scale = anchor.get_actor_scale3d()
    existing = next((actor for actor in actors if actor.get_actor_label() == label), None)
    if existing is not None:
        component = existing.get_editor_property("static_mesh_component")
        changed = False
        if component.get_editor_property("static_mesh") != mesh:
            if request["request_id"] not in [str(tag) for tag in existing.tags]:
                fail("existing surface-detail actor points to another request")
            component.set_static_mesh(mesh)
            changed = True
        for slot in range(component.get_num_materials()):
            if component.get_material(slot) != engine_material:
                component.set_material(slot, engine_material)
                changed = True
        # The projected mesh uses the same Blender scene coordinates as the
        # registered baked surface, so its carrier inherits that scene Actor's
        # transform. Object-local projection transforms are already in vertices.
        if existing.get_actor_location() != anchor_location:
            existing.set_actor_location(anchor_location, False, False)
            changed = True
        if existing.get_actor_rotation() != anchor_rotation:
            existing.set_actor_rotation(anchor_rotation, False)
            changed = True
        if existing.get_actor_scale3d() != anchor_scale:
            existing.set_actor_scale3d(anchor_scale)
            changed = True
        existing.set_is_temporarily_hidden_in_editor(False)
        existing.set_actor_hidden_in_game(False)
        component.set_visibility(True)
        component.set_hidden_in_game(False)
        return 0, int(changed)
    actor = subsystem.spawn_actor_from_object(mesh, anchor_location, anchor_rotation)
    actor.set_actor_label(label)
    actor.set_actor_scale3d(anchor_scale)
    actor.get_editor_property("static_mesh_component").set_material(0, engine_material)
    actor.set_is_temporarily_hidden_in_editor(False)
    actor.set_actor_hidden_in_game(False)
    actor.tags = ["ArtFlow.SurfaceDetail", request["request_id"], request["target_object"]]
    return 1, 0


first_created, first_updated = apply_projection()
repeat_created, repeat_updated = apply_projection()
if repeat_created != 0 or repeat_updated != 0:
    fail("repeated surface-detail application created another Actor")
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
actors = subsystem.get_all_level_actors()
projected_actor = next(
    (actor for actor in actors if actor.get_actor_label() == "ArtFlow_Projected_Inlay"),
    None,
)
surface_actor = next(
    (actor for actor in actors if actor.get_actor_label() == surface_return["actor_label"]),
    None,
)
if not isinstance(projected_actor, unreal.StaticMeshActor) or not isinstance(
    surface_actor, unreal.StaticMeshActor
):
    fail("surface-detail or baked-surface Actor is missing after application")
projected_origin, projected_extent = projected_actor.get_actor_bounds(False)
surface_origin, surface_extent = surface_actor.get_actor_bounds(False)
projected_component = projected_actor.get_editor_property("static_mesh_component")
camera = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_Camera"), None)
if not isinstance(camera, unreal.CameraActor):
    fail("registered camera is missing")
screenshot = evidence / "unreal-surface-detail-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
unreal.AutomationLibrary.take_high_res_screenshot(
    1280, 720, str(screenshot), camera, False, False
)
source_after = sha256(source_map)
if source_after != source_before:
    fail("source level changed during surface-detail return")
assets = unreal.EditorAssetLibrary.list_assets(destination, recursive=True)
materials = [
    path
    for path in assets
    if isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.MaterialInterface)
]
textures = [
    path
    for path in assets
    if isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.Texture)
]
facts = {
    "schema_id": "artflow-unreal-surface-detail-return-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "comfy_receipt_sha256": comfy_receipt["receipt_sha256"],
    "blender_receipt_sha256": blender_receipt["receipt_sha256"],
    "status": "reconciled" if asset_reconciled and candidate_reconciled and first_created == 0 else "imported",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "source_candidate_scene_path": dressing_return["candidate_scene_path"],
    "candidate_scene_path": candidate_package,
    "static_mesh_path": mesh.get_path_name(),
    "material_paths": materials,
    "texture_paths": textures,
    "created_actor_count": first_created,
    "updated_actor_count": first_updated,
    "repeat_created_actor_count": repeat_created,
    "repeat_updated_actor_count": repeat_updated,
    "projected_actor_bounds_cm": {
        "origin": [projected_origin.x, projected_origin.y, projected_origin.z],
        "extent": [projected_extent.x, projected_extent.y, projected_extent.z],
    },
    "surface_actor_bounds_cm": {
        "origin": [surface_origin.x, surface_origin.y, surface_origin.z],
        "extent": [surface_extent.x, surface_extent.y, surface_extent.z],
    },
    "projected_material_path": projected_component.get_material(0).get_path_name(),
    "projected_component_visible": projected_component.is_visible(),
    "source_level_sha256_before": source_before,
    "source_level_sha256_after": source_after,
    "screenshot_path": screenshot.name,
    "screenshot_sha256": None,
    "capture_status": "requested",
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
facts["receipt_sha256"] = canonical(facts)
(evidence / "unreal-surface-detail-return-receipt.json").write_text(
    json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(
    f"ARTFLOW_UNREAL_SURFACE_DETAIL_SUCCEEDED candidate={candidate_package} "
    f"created={first_created} repeat_created={repeat_created}"
)
