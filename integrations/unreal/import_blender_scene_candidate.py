from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import unreal


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow Blender candidate failed: {message}")


repo_root = Path(__file__).resolve().parents[2]
evidence_root = repo_root / "artifacts/goal/m23-s1-blender-modeling"
request = json.loads((evidence_root / "modeling-request.json").read_text(encoding="utf-8"))
receipt = json.loads((evidence_root / "modeling-receipt.json").read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-blender-modeling-request/1":
    fail("建模请求版本不受支持")
if receipt.get("request_sha256") != request.get("request_sha256"):
    fail("Blender 回执与当前建模请求不一致")
glb_artifact = next((item for item in receipt["artifacts"] if item["kind"] == "glb"), None)
if glb_artifact is None:
    fail("Blender 回执没有 GLB 产物")
glb_path = (evidence_root / glb_artifact["relative_path"]).resolve()
if evidence_root.resolve() not in glb_path.parents or file_sha256(glb_path) != glb_artifact["sha256"]:
    fail("GLB 文件身份与 Blender 回执不一致")

project_root = Path(unreal.Paths.project_dir()).resolve()
source_map = project_root / "Content/ArtFlowDemo.umap"
source_before = file_sha256(source_map)
if source_before != request["source_level_sha256"]:
    fail("源关卡已变化，未执行 Blender 资产回流")

identity = request["request_sha256"][:12]
destination_root = f"/Game/ArtFlow/Generated/Blender/B_{identity}"
asset_name = "SM_AF_WeatheredShrine"
existing_assets = unreal.EditorAssetLibrary.list_assets(destination_root, recursive=True)
mesh = None
for asset_path in existing_assets:
    candidate = unreal.EditorAssetLibrary.load_asset(asset_path)
    if isinstance(candidate, unreal.StaticMesh) and unreal.EditorAssetLibrary.get_metadata_tag(
        candidate, "ArtFlow.BlenderRequestSha256"
    ) == request["request_sha256"]:
        mesh = candidate
        break
reconciled = mesh is not None
imported_paths: list[str] = []
if mesh is None:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(glb_path))
    task.set_editor_property("destination_path", destination_root)
    task.set_editor_property("destination_name", asset_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported_paths = list(task.get_editor_property("imported_object_paths"))
    for object_path in imported_paths:
        candidate = unreal.EditorAssetLibrary.load_asset(object_path)
        if isinstance(candidate, unreal.StaticMesh):
            mesh = candidate
            break
if not isinstance(mesh, unreal.StaticMesh):
    fail(f"Unreal Interchange 没有生成 StaticMesh：{imported_paths}")

mesh_path = mesh.get_path_name()
unreal.EditorAssetLibrary.set_metadata_tag(
    mesh, "ArtFlow.BlenderRequestSha256", request["request_sha256"]
)
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.SourceGLBSha256", glb_artifact["sha256"])
unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.Generator", receipt["capability_id"])
mesh_library = unreal.EditorStaticMeshLibrary
if mesh_library.get_convex_collision_count(mesh) == 0:
    mesh_library.add_simple_collisions(mesh, unreal.ScriptingCollisionShapeType.NDOP10_X)
unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)

candidate_name = f"Blender_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
if not unreal.EditorAssetLibrary.does_asset_exist(candidate_object):
    world_asset = unreal.EditorAssetLibrary.duplicate_asset("/Game/ArtFlowDemo", candidate_package)
    if world_asset is None:
        fail("无法创建 Blender 隔离候选关卡")
    unreal.EditorAssetLibrary.save_loaded_asset(world_asset, only_if_is_dirty=False)
    del world_asset
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("无法打开 Blender 隔离候选关卡")
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsystem.get_all_level_actors()
actor_label = "ArtFlow_Blender_WeatheredShrine"
actor = next((item for item in actors if item.get_actor_label() == actor_label), None)
actor_reconciled = actor is not None
bounds = mesh.get_bounds().box_extent
location = unreal.Vector(450.0, 0.0, 0.0)
if actor is None:
    actor = actor_subsystem.spawn_actor_from_object(mesh, location, unreal.Rotator())
    if actor is None:
        fail("无法把 Blender StaticMesh 放入候选关卡")
actor.set_actor_label(actor_label)
actor.set_actor_location(location, False, False)
actor.tags = ["ArtFlow.BlenderGenerated", request["request_id"]]

camera_label = "ArtFlow_Blender_Camera"
camera = next((item for item in actors if item.get_actor_label() == camera_label), None)
camera_location = unreal.Vector(1200.0, -1450.0, 720.0)
target = unreal.Vector(450.0, 0.0, 150.0)
camera_rotation = unreal.MathLibrary.find_look_at_rotation(camera_location, target)
if camera is None:
    camera = actor_subsystem.spawn_actor_from_class(
        unreal.CameraActor, camera_location, camera_rotation
    )
camera.set_actor_label(camera_label)
camera.set_actor_location(camera_location, False, False)
camera.set_actor_rotation(camera_rotation, False)
camera.get_editor_property("camera_component").set_editor_property("field_of_view", 45.0)
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

screenshot_path = evidence_root / "unreal-blender-candidate.png"
task = unreal.AutomationLibrary.take_high_res_screenshot(
    1280, 720, str(screenshot_path), camera, False, False
)
deadline = time.time() + 25.0
while not task.is_task_done() and time.time() < deadline:
    time.sleep(0.1)
flush_deadline = time.time() + 3.0
while not screenshot_path.is_file() and time.time() < flush_deadline:
    time.sleep(0.1)
if not screenshot_path.is_file():
    fail("Unreal 未生成 Blender 候选截图")
source_after = file_sha256(source_map)
if source_after != source_before:
    fail("Blender 候选回流期间源关卡发生变化")

result = {
    "schema_id": "artflow-unreal-blender-candidate-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "blender_receipt_sha256": receipt["receipt_sha256"],
    "status": "reconciled" if reconciled and actor_reconciled else "imported",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "static_mesh_path": mesh_path,
    "candidate_scene_path": candidate_package,
    "actor_label": actor_label,
    "vertex_count": mesh_library.get_number_verts(mesh, 0),
    "triangle_count": mesh.get_num_triangles(0),
    "material_slot_count": len(mesh.get_editor_property("static_materials")),
    "simple_collision_count": mesh_library.get_convex_collision_count(mesh),
    "source_level_sha256_before": source_before,
    "source_level_sha256_after": source_after,
    "screenshot_sha256": file_sha256(screenshot_path),
    "duplicate_side_effect_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical_sha256(result)
(evidence_root / "unreal-return-receipt.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
unreal.log(
    f"ARTFLOW_BLENDER_UNREAL_RETURN status={result['status']} mesh={mesh_path} candidate={candidate_package}"
)
