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
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow damage variant failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m55-s1-damage-variant"
request = json.loads((evidence / "damage-variant-request.json").read_text(encoding="utf-8"))
comfy = json.loads((evidence / "comfy-damage-field-receipt.json").read_text(encoding="utf-8"))
blender = json.loads((evidence / "blender-damage-variant-receipt.json").read_text(encoding="utf-8"))
manifest_path = evidence / next(
    item["relative_path"] for item in blender["artifacts"] if item["kind"] == "manifest"
)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if (
    comfy["request_sha256"] != request["request_sha256"]
    or blender["request_sha256"] != request["request_sha256"]
    or blender["comfy_receipt_sha256"] != comfy["receipt_sha256"]
):
    fail("request and host receipts do not form one identity chain")
for item in blender["artifacts"]:
    if sha256(evidence / item["relative_path"]) != item["sha256"]:
        fail(f"Blender artifact identity changed: {item['relative_path']}")
if manifest["triangle_count"] > request["triangle_budget"]:
    fail("damaged asset exceeds the registered triangle budget")
if manifest["uv_layer"] != "UVMap" or not manifest["material_slots"]:
    fail("damaged asset is missing required UV or material data")

project = Path(unreal.Paths.project_dir()).resolve()
source_file = project / "Content" / (
    request["source_candidate_scene_path"].removeprefix("/Game/") + ".umap"
)
source_before = sha256(source_file)
if source_before != request["source_candidate_sha256"]:
    fail("source candidate changed after request compilation")

identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Blender/Damage/D_{identity}"
mesh = None
assets_reconciled = True
for asset_path in unreal.EditorAssetLibrary.list_assets(
    destination, recursive=True, include_folder=False
):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if isinstance(asset, unreal.StaticMesh) and (
        unreal.EditorAssetLibrary.get_metadata_tag(asset, "ArtFlow.DamageRequestSha256")
        == request["request_sha256"]
    ):
        mesh = asset
        break
if mesh is None:
    assets_reconciled = False
    glb = evidence / next(
        item["relative_path"] for item in blender["artifacts"] if item["kind"] == "glb"
    )
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(glb))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", "SM_AF_Module_Gateway_Damaged")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    mesh = next(
        (
            unreal.EditorAssetLibrary.load_asset(path)
            for path in task.get_editor_property("imported_object_paths")
            if isinstance(unreal.EditorAssetLibrary.load_asset(path), unreal.StaticMesh)
        ),
        None,
    )
if not isinstance(mesh, unreal.StaticMesh):
    fail("Interchange did not produce the registered damaged mesh")
unreal.EditorAssetLibrary.set_metadata_tag(
    mesh, "ArtFlow.DamageRequestSha256", request["request_sha256"]
)
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.SourceModule", request["target_object"])
if unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh) == 0:
    unreal.EditorStaticMeshLibrary.add_simple_collisions(
        mesh, unreal.ScriptingCollisionShapeType.BOX
    )
unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
collision_count = unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh)
material_slot_count = len(mesh.get_editor_property("static_materials"))
if collision_count < 1 or material_slot_count < 1:
    fail("damaged mesh is missing collision or a material slot after import")

candidate_name = f"Damage_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(
        request["source_candidate_scene_path"], candidate_package
    )
    if candidate is None:
        fail("could not derive the damage candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()

world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
target = next(
    (actor for actor in actors if actor.get_actor_label() == request["target_actor_label"]),
    None,
)
if target is None:
    fail("registered target actor is missing from the derived candidate")
component = target.get_component_by_class(unreal.StaticMeshComponent)
if not isinstance(component, unreal.StaticMeshComponent):
    fail("registered target actor has no static mesh component")
updated_actor_count = 0
current_mesh = component.get_editor_property("static_mesh")
if (
    not isinstance(current_mesh, unreal.StaticMesh)
    or current_mesh.get_path_name() != mesh.get_path_name()
):
    component.set_static_mesh(mesh)
    updated_actor_count = 1
target.tags = [
    "ArtFlow.DamageVariant",
    request["request_id"],
    request["target_module_id"],
]

preview_label = "ArtFlow_DamageHeroPreview"
preview_actor = next(
    (actor for actor in actors if actor.get_actor_label() == preview_label), None
)
created_actor_count = 0
if preview_actor is None:
    preview_actor = subsystem.spawn_actor_from_object(
        mesh, unreal.Vector(-850.0, -750.0, 25.0), unreal.Rotator(0.0, 0.0, 0.0)
    )
    preview_actor.set_actor_label(preview_label)
    created_actor_count = 1
preview_component = preview_actor.get_component_by_class(unreal.StaticMeshComponent)
if not isinstance(preview_component, unreal.StaticMeshComponent):
    fail("damage preview actor has no static mesh component")
preview_component.set_static_mesh(mesh)
preview_actor.set_actor_rotation(
    unreal.Rotator(roll=0.0, pitch=0.0, yaw=180.0), False
)
preview_actor.tags = ["ArtFlow.DamagePreview", request["request_id"]]

camera = next(
    (actor for actor in actors if actor.get_actor_label() == "ArtFlow_Camera"), None
)
if not isinstance(camera, unreal.CameraActor):
    fail("candidate camera is unavailable for matched evidence")
preview_location = preview_actor.get_actor_location()
camera_location = preview_location + unreal.Vector(520.0, -920.0, 320.0)
camera.set_actor_location(camera_location, False, False)
camera.set_actor_rotation(
    unreal.MathLibrary.find_look_at_rotation(
        camera_location, preview_location + unreal.Vector(0.0, 0.0, 205.0)
    ),
    False,
)
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

screenshot = evidence / "unreal-damage-variant-candidate.png"
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
        fail("damage route changed the upstream modular candidate")
    loaded_actors = subsystem.get_all_level_actors()
    loaded_target = next(
        (
            actor
            for actor in loaded_actors
            if actor.get_actor_label() == request["target_actor_label"]
        ),
        None,
    )
    loaded_component = (
        loaded_target.get_component_by_class(unreal.StaticMeshComponent)
        if loaded_target is not None
        else None
    )
    if (
        not isinstance(loaded_component, unreal.StaticMeshComponent)
        or not isinstance(
            loaded_component.get_editor_property("static_mesh"), unreal.StaticMesh
        )
        or loaded_component.get_editor_property("static_mesh").get_path_name()
        != mesh.get_path_name()
    ):
        fail("damaged mesh did not persist on the target actor")
    result = {
        "schema_id": "artflow-unreal-damage-variant-receipt/1",
        "request_sha256": request["request_sha256"],
        "comfy_receipt_sha256": comfy["receipt_sha256"],
        "blender_receipt_sha256": blender["receipt_sha256"],
        "status": (
            "reconciled"
            if (
                assets_reconciled
                and candidate_reconciled
                and updated_actor_count == 0
                and created_actor_count == 0
            )
            else "generated"
        ),
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "source_candidate_scene_path": request["source_candidate_scene_path"],
        "candidate_scene_path": candidate_package,
        "mesh_path": mesh.get_path_name(),
        "target_actor_label": request["target_actor_label"],
        "preview_actor_label": preview_label,
        "updated_actor_count": updated_actor_count,
        "created_actor_count": created_actor_count,
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
    (evidence / "unreal-damage-variant-receipt.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    unreal.log(
        f"ARTFLOW_DAMAGE_RETURN status={result['status']} "
        f"triangles={manifest['triangle_count']} collision={collision_count}"
    )
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta: float) -> None:
    if state["finished"]:
        return
    state["ticks"] += 1
    if state["ticks"] == 2:
        unreal.AutomationLibrary.take_high_res_screenshot(
            1280, 720, str(screenshot), camera, False, False
        )
    if screenshot.is_file() or state["ticks"] > 240:
        finish()


state["callback"] = unreal.register_slate_post_tick_callback(on_tick)
