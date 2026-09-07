from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import unreal


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow procedural kit return failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m32-s1-procedural-kit"
request = json.loads((evidence / "procedural-kit-request.json").read_text(encoding="utf-8"))
receipt = json.loads((evidence / "procedural-kit-receipt.json").read_text(encoding="utf-8"))
if request.get("consumer_capability_id") != "unreal.pcg.modular_kit_scatter.v1":
    fail("request is not addressed to the registered PCG consumer")
if receipt.get("request_sha256") != request.get("request_sha256"):
    fail("Blender receipt does not belong to this request")
for variant in receipt["variants"]:
    for key, hash_key in (("base_glb", "base_sha256"), ("lod1_glb", "lod1_sha256")):
        path = evidence / variant[key]
        if sha256(path) != variant[hash_key]:
            fail(f"registered mesh identity drifted: {variant[key]}")

project = Path(unreal.Paths.project_dir()).resolve()
source_map = project / "Content/ArtFlowDemo.umap"
source_before = sha256(source_map)
if source_before != request["source_level_sha256"]:
    fail("source level changed after kit request compilation")

identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Blender/Kits/K_{identity}"
meshes: dict[str, unreal.StaticMesh] = {}
imported_assets: list[str] = []
lod_results: dict[str, int] = {}
collision_counts: dict[str, int] = {}
assets_reconciled = True
for variant in receipt["variants"]:
    expected_name = variant["object_name"]
    mesh = None
    for asset_path in unreal.EditorAssetLibrary.list_assets(destination, recursive=True):
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if (
            isinstance(asset, unreal.StaticMesh)
            and unreal.EditorAssetLibrary.get_metadata_tag(asset, "ArtFlow.ProceduralKitRequestSha256")
            == request["request_sha256"]
            and unreal.EditorAssetLibrary.get_metadata_tag(asset, "ArtFlow.KitVariantId")
            == variant["variant_id"]
        ):
            mesh = asset
            break
    if mesh is None:
        assets_reconciled = False
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(evidence / variant["base_glb"]))
        task.set_editor_property("destination_path", destination)
        task.set_editor_property("destination_name", expected_name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", False)
        task.set_editor_property("save", True)
        unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
        for asset_path in task.get_editor_property("imported_object_paths"):
            asset = unreal.EditorAssetLibrary.load_asset(asset_path)
            if isinstance(asset, unreal.StaticMesh):
                mesh = asset
                break
    if not isinstance(mesh, unreal.StaticMesh):
        fail(f"Interchange did not produce {expected_name}")
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.ProceduralKitRequestSha256", request["request_sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.KitVariantId", variant["variant_id"])
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.LOD1Sha256", variant["lod1_sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.CollisionPolicy", request["collision_policy"])
    current_lods = unreal.EditorStaticMeshLibrary.get_lod_count(mesh)
    if current_lods < 2:
        imported_lod = unreal.EditorStaticMeshLibrary.import_lod(mesh, 1, str(evidence / variant["lod1_glb"]))
        if imported_lod != 1:
            fail(f"could not attach registered LOD1 for {variant['variant_id']}")
    if unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh) == 0:
        unreal.EditorStaticMeshLibrary.add_simple_collisions(mesh, unreal.ScriptingCollisionShapeType.BOX)
    unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
    meshes[variant["variant_id"]] = mesh
    imported_assets.append(mesh.get_path_name())
    lod_results[variant["variant_id"]] = unreal.EditorStaticMeshLibrary.get_lod_count(mesh)
    collision_counts[variant["variant_id"]] = unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh)

candidate_name = f"Kit_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    duplicated = unreal.EditorAssetLibrary.duplicate_asset(request["source_candidate_scene_path"], candidate_package)
    if duplicated is None:
        fail("could not duplicate registered detail candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(duplicated, only_if_is_dirty=False)
    del duplicated
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load procedural-kit candidate")
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
anchor = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_SurfaceDetail_Inlay"), None)
anchor_location = anchor.get_actor_location() if anchor is not None else unreal.Vector(0, 0, 0)
created = 0
updated = 0
placement_identities = []
for point in receipt["placements"]:
    label = f"ArtFlow_PCG_{point['point_id']}"
    actor = next((item for item in actors if item.get_actor_label() == label), None)
    mesh = meshes[point["variant_id"]]
    location = point["location_m"]
    target_location = unreal.Vector(
        anchor_location.x + location[0] * 100,
        anchor_location.y - location[1] * 100,
        max(0.0, anchor_location.z - 139.2) + location[2] * 100,
    )
    target_rotation = unreal.Rotator(0, -point["yaw_deg"], 0)
    target_scale = unreal.Vector(point["scale"], point["scale"], point["scale"])
    if actor is None:
        actor = subsystem.spawn_actor_from_object(mesh, target_location, target_rotation)
        created += 1
    component = actor.get_editor_property("static_mesh_component")
    needs_update = (
        component.get_editor_property("static_mesh") != mesh
        or (actor.get_actor_location() - target_location).length() > 0.01
    )
    if needs_update and actor.get_actor_label() == label:
        component.set_editor_property("static_mesh", mesh)
        actor.set_actor_location(target_location, False, False)
        updated += 1
    actor.set_actor_label(label)
    actor.set_actor_rotation(target_rotation, False)
    actor.set_actor_scale3d(target_scale)
    actor.tags = ["ArtFlow.PCG", request["request_id"], point["point_id"], point["variant_id"]]
    placement_identities.append({"point_id": point["point_id"], "actor_label": label, "mesh_path": mesh.get_path_name()})
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

camera = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_Camera"), None)
screenshot = evidence / "unreal-procedural-kit-candidate.png"
if isinstance(camera, unreal.CameraActor):
    if screenshot.is_file():
        screenshot.unlink()
    unreal.AutomationLibrary.take_high_res_screenshot(1280, 720, str(screenshot), camera, False, False)
source_after = sha256(source_map)
if source_after != source_before:
    fail("source level changed during procedural-kit return")
result = {
    "schema_id": "artflow-unreal-procedural-kit-return-receipt/1",
    "request_id": request["request_id"], "request_sha256": request["request_sha256"],
    "blender_receipt_sha256": receipt["receipt_sha256"],
    "consumer_capability_id": request["consumer_capability_id"],
    "status": "reconciled" if assets_reconciled and candidate_reconciled and created == 0 and updated == 0 else "placed",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "source_candidate_scene_path": request["source_candidate_scene_path"],
    "candidate_scene_path": candidate_package, "imported_mesh_paths": sorted(imported_assets),
    "lod_counts": lod_results, "collision_counts": collision_counts,
    "pcg_operation": {"seed": request["seed"], "point_count": len(receipt["placements"]), "placements": placement_identities},
    "created_actor_count": created, "updated_actor_count": updated,
    "duplicate_side_effect_count": 0,
    "source_level_sha256_before": source_before, "source_level_sha256_after": source_after,
    "screenshot_path": screenshot.name, "screenshot_sha256": None, "capture_status": "requested",
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical(result)
(evidence / "unreal-procedural-kit-return-receipt.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
unreal.log(f"ARTFLOW_PROCEDURAL_KIT_RETURN status={result['status']} candidate={candidate_package} points={len(placement_identities)}")
