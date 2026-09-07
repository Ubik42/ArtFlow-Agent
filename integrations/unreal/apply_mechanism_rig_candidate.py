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
    raise RuntimeError(f"ArtFlow mechanism rig return failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m51-s1-mechanism-rig"
request = json.loads((evidence / "mechanism-rig-request.json").read_text(encoding="utf-8"))
blender = json.loads(
    (evidence / "blender-mechanism-rig-receipt.json").read_text(encoding="utf-8")
)
manifest_path = evidence / next(
    item["relative_path"] for item in blender["artifacts"] if item["kind"] == "manifest"
)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if request["unreal_capability_id"] != "unreal.skeletal.mechanism_import.v1":
    fail("request is not addressed to the registered Unreal mechanism capability")
if blender["request_sha256"] != request["request_sha256"]:
    fail("Blender receipt does not belong to this request")
if manifest["request_sha256"] != request["request_sha256"]:
    fail("mechanism manifest does not belong to this request")
for item in blender["artifacts"]:
    artifact = evidence / item["relative_path"]
    if not artifact.is_file() or sha256(artifact) != item["sha256"]:
        fail(f"Blender artifact identity drifted: {item['relative_path']}")
if manifest["triangle_count"] > request["triangle_budget"]:
    fail("mechanism exceeds the registered geometry budget")
if {item["bone_name"] for item in manifest["bones"]} != {
    "root",
    "hinge_left",
    "hinge_right",
}:
    fail("mechanism manifest differs from the registered bone catalog")

project = Path(unreal.Paths.project_dir()).resolve()
source_file = (
    project
    / "Content"
    / (request["source_candidate_scene_path"].removeprefix("/Game/") + ".umap")
)
source_before = sha256(source_file)
if source_before != request["source_candidate_sha256"]:
    fail("source spline candidate changed after request compilation")

identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Blender/Mechanism/RigV2_{identity}"
tag_name = "ArtFlow.MechanismRequestSha256"
assets_reconciled = True
skeletal_mesh = None
skeleton = None
animation = None
for asset_path in unreal.EditorAssetLibrary.list_assets(
    destination, recursive=True, include_folder=False
):
    asset = unreal.EditorAssetLibrary.load_asset(asset_path)
    if unreal.EditorAssetLibrary.get_metadata_tag(asset, tag_name) != request["request_sha256"]:
        continue
    if isinstance(asset, unreal.SkeletalMesh):
        skeletal_mesh = asset
    elif isinstance(asset, unreal.Skeleton):
        skeleton = asset
    elif isinstance(asset, unreal.AnimSequence):
        animation = asset

if skeletal_mesh is None or animation is None:
    assets_reconciled = False
    fbx = evidence / next(
        item["relative_path"] for item in blender["artifacts"] if item["kind"] == "fbx"
    )
    options = unreal.FbxImportUI()
    options.set_editor_property("automated_import_should_detect_type", False)
    options.set_editor_property("import_mesh", True)
    options.set_editor_property("import_as_skeletal", True)
    options.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    options.set_editor_property("original_import_type", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
    options.set_editor_property("import_materials", False)
    options.set_editor_property("import_textures", False)
    options.set_editor_property("import_animations", True)
    options.set_editor_property("create_physics_asset", False)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(fbx))
    task.set_editor_property("destination_path", destination)
    task.set_editor_property("destination_name", "SK_AF_ArticulatedGate")
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    task.set_editor_property("options", options)
    task.set_editor_property("factory", unreal.FbxFactory())
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    produced_paths = list(task.get_editor_property("imported_object_paths"))
    discovered_paths = list(
        unreal.EditorAssetLibrary.list_assets(
            destination, recursive=True, include_folder=False
        )
    )
    for asset_path in dict.fromkeys(produced_paths + discovered_paths):
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if isinstance(asset, unreal.SkeletalMesh):
            skeletal_mesh = asset
        elif isinstance(asset, unreal.Skeleton):
            skeleton = asset
        elif isinstance(asset, unreal.AnimSequence):
            animation = asset

if not isinstance(skeletal_mesh, unreal.SkeletalMesh):
    fail("FBX import did not produce a skeletal mesh")
if skeleton is None:
    skeleton = skeletal_mesh.get_editor_property("skeleton")
if not isinstance(skeleton, unreal.Skeleton):
    fail("FBX import did not produce a skeleton")
if not isinstance(animation, unreal.AnimSequence):
    fail("FBX import did not produce an animation sequence")

bone_names = [str(name) for name in skeleton.get_reference_pose().get_bone_names()]
expected_bones = [item["bone_name"] for item in manifest["bones"]]
transport_root = None
if bone_names == expected_bones:
    verified_bones = bone_names
elif len(bone_names) == len(expected_bones) + 1 and bone_names[1:] == expected_bones:
    # Blender's FBX writer serializes the Armature object as a transport root.
    # The authored deform hierarchy remains unchanged beneath it.
    transport_root = bone_names[0]
    verified_bones = bone_names[1:]
else:
    fail(f"imported hierarchy differs from manifest: {bone_names}")
for asset in (skeletal_mesh, skeleton, animation):
    unreal.EditorAssetLibrary.set_metadata_tag(asset, tag_name, request["request_sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(asset, "ArtFlow.MechanismType", request["mechanism_type"])
    unreal.EditorAssetLibrary.save_loaded_asset(asset, only_if_is_dirty=False)

candidate_name = f"Mechanism_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(
        request["source_candidate_scene_path"], candidate_package
    )
    if candidate is None:
        fail("could not derive the isolated mechanism candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()

world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load the mechanism candidate")
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
actor_label = "ArtFlow_Mechanism_ArticulatedGate"
actor = next((item for item in actors if item.get_actor_label() == actor_label), None)
created = 0
updated = 0
asset_bounds = skeletal_mesh.get_bounds()
asset_extent = asset_bounds.box_extent
asset_width = float(asset_extent.x) * 2.0
expected_width = float(request["width_cm"] + 112)
unit_scale = expected_width / asset_width
if not 0.01 <= unit_scale <= 200.0:
    fail(f"FBX unit adaptation is outside the registered range: {unit_scale}")
target_location = unreal.Vector(2500, 0, 20)
target_rotation = unreal.Rotator(roll=0, pitch=0, yaw=0)
if actor is None:
    actor = subsystem.spawn_actor_from_class(
        unreal.SkeletalMeshActor, target_location, target_rotation
    )
    actor.set_actor_label(actor_label)
    created += 1
component = actor.get_editor_property("skeletal_mesh_component")
if component.get_editor_property("skeletal_mesh_asset") != skeletal_mesh:
    component.set_editor_property("skeletal_mesh_asset", skeletal_mesh)
    updated += 1
component.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
component.set_animation(animation)
component.set_position((request["frame_open"] - request["frame_start"]) / request["fps"], False)
component.set_editor_property("pause_anims", True)
actor.set_actor_location(target_location, False, False)
actor.set_actor_rotation(target_rotation, False)
actor.set_actor_scale3d(unreal.Vector(unit_scale, unit_scale, unit_scale))
actor.tags = ["ArtFlow.Mechanism", request["request_id"], request["mechanism_type"]]

camera_label = "ArtFlow_Mechanism_Camera"
camera = next((item for item in actors if item.get_actor_label() == camera_label), None)
if camera is None:
    camera = subsystem.spawn_actor_from_class(
        unreal.CameraActor,
        unreal.Vector(2500, -950, 330),
        unreal.Rotator(roll=0, pitch=0, yaw=0),
    )
    camera.set_actor_label(camera_label)
    created += 1
camera_location = unreal.Vector(2500, -950, 330)
camera.set_actor_location(camera_location, False, False)
camera.set_actor_rotation(
    unreal.MathLibrary.find_look_at_rotation(camera_location, unreal.Vector(2500, 0, 190)),
    False,
)
camera.get_editor_property("camera_component").set_editor_property("field_of_view", 48.0)
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

screenshot = evidence / "unreal-mechanism-rig-candidate.png"
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
        fail("mechanism return changed the upstream spline candidate")
    current = subsystem.get_all_level_actors()
    mechanism_count = sum(1 for item in current if item.get_actor_label() == actor_label)
    if mechanism_count != 1:
        fail("candidate does not contain exactly one registered mechanism actor")
    play_length = float(animation.get_play_length())
    result = {
        "schema_id": "artflow-unreal-mechanism-rig-receipt/1",
        "request_sha256": request["request_sha256"],
        "blender_receipt_sha256": blender["receipt_sha256"],
        "status": "reconciled"
        if assets_reconciled and candidate_reconciled and created == 0 and updated == 0
        else "generated",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "source_candidate_scene_path": request["source_candidate_scene_path"],
        "candidate_scene_path": candidate_package,
        "skeletal_mesh_path": skeletal_mesh.get_path_name(),
        "skeleton_path": skeleton.get_path_name(),
        "animation_path": animation.get_path_name(),
        "bone_names": bone_names,
        "verified_deform_bones": verified_bones,
        "fbx_transport_root": transport_root,
        "animation_play_length_seconds": round(play_length, 4),
        "asset_bounds_extent": [
            round(float(asset_extent.x), 4),
            round(float(asset_extent.y), 4),
            round(float(asset_extent.z), 4),
        ],
        "unit_adapter_scale": round(unit_scale, 6),
        "actor_label": actor_label,
        "mechanism_actor_count": mechanism_count,
        "created_actor_count": created,
        "updated_actor_count": updated,
        "duplicate_side_effect_count": 0,
        "source_candidate_sha256_before": source_before,
        "source_candidate_sha256_after": source_after,
        "screenshot_path": screenshot.name,
        "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
        "capture_status": "captured" if screenshot.is_file() else "unavailable",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-mechanism-rig-receipt.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    unreal.log(
        f"ARTFLOW_MECHANISM_RETURN status={result['status']} bones={len(bone_names)} animation={animation.get_name()}"
    )
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta: float) -> None:
    state["ticks"] += 1
    if state["ticks"] == 2:
        unreal.AutomationLibrary.take_high_res_screenshot(
            1280, 720, str(screenshot), camera, False, False
        )
    if screenshot.is_file() or state["ticks"] > 240:
        finish()


state["callback"] = unreal.register_slate_post_tick_callback(on_tick)
