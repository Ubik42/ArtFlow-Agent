from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import unreal


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow generated mesh staging failed closed: {message}")


repo_root = Path(os.environ["ARTFLOW_REPO_ROOT"]).resolve()
evidence_root = repo_root / "artifacts/goal/m10-s2-image-to-3d"
request = json.loads((evidence_root / "unreal-admission-request.json").read_text(encoding="utf-8"))
admission = json.loads(
    (evidence_root / "unreal-admission-receipt.json").read_text(encoding="utf-8")
)
if admission.get("request_sha256") != request.get("request_sha256"):
    fail("staging is not bound to the verified Interchange admission")
project_root = Path(unreal.Paths.project_dir()).resolve()
source_file = project_root / "Content/ArtFlowDemo.umap"
source_before = file_sha256(source_file)
if source_before != request.get("source_scene_sha256"):
    fail("source scene changed before staging")

candidate_path = "/Game/ArtFlow/Staging/AF_M10_86bcc31c4daa"
candidate_object = candidate_path + ".AF_M10_86bcc31c4daa"
if not unreal.EditorAssetLibrary.does_asset_exist(candidate_object):
    duplicated = unreal.EditorAssetLibrary.duplicate_asset("/Game/ArtFlowDemo", candidate_path)
    if duplicated is None:
        fail("could not create isolated M10 candidate level")
    unreal.EditorAssetLibrary.save_loaded_asset(duplicated, only_if_is_dirty=False)
    del duplicated
    unreal.SystemLibrary.collect_garbage()
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_path)
if world is None:
    fail("could not load isolated M10 candidate level")
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsystem.get_all_level_actors()
mesh = unreal.EditorAssetLibrary.load_asset(admission["static_mesh_path"])
if not isinstance(mesh, unreal.StaticMesh):
    fail("admitted StaticMesh is unavailable")
label = "ArtFlow_M10_GeneratedAltar"
actor = next((item for item in actors if item.get_actor_label() == label), None)
reconciled = actor is not None
scale = float(request["unreal_uniform_scale"])
bounds = mesh.get_bounds().box_extent
location = unreal.Vector(350.0, 0.0, bounds.z * scale)
if actor is None:
    actor = actor_subsystem.spawn_actor_from_object(mesh, location, unreal.Rotator(0.0, 0.0, 0.0))
    if actor is None:
        fail("could not place admitted mesh in candidate level")
actor.set_actor_label(label)
actor.set_actor_location(location, False, False)
actor.set_actor_scale3d(unreal.Vector(scale, scale, scale))
actor.tags = ["ArtFlow.GeneratedMesh", request["request_id"]]

camera_label = "ArtFlow_M10_GeneratedAltar_Camera"
camera = next((item for item in actors if item.get_actor_label() == camera_label), None)
camera_location = unreal.Vector(350.0, -500.0, 210.0)
target = unreal.Vector(350.0, 0.0, 80.0)
camera_rotation = unreal.MathLibrary.find_look_at_rotation(camera_location, target)
if camera is None:
    camera = actor_subsystem.spawn_actor_from_class(
        unreal.CameraActor, camera_location, camera_rotation
    )
camera.set_actor_label(camera_label)
camera.set_actor_location(camera_location, False, False)
camera.set_actor_rotation(camera_rotation, False)
camera.get_editor_property("camera_component").set_editor_property("field_of_view", 35.0)
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_path)

screenshot = evidence_root / "unreal-generated-altar-v3.png"
if not screenshot.is_file():
    task = unreal.AutomationLibrary.take_high_res_screenshot(
        1280, 720, str(screenshot), camera, False, False
    )
    deadline = time.time() + 20.0
    while not task.is_task_done() and time.time() < deadline:
        time.sleep(0.1)
if not screenshot.is_file():
    fail("UE screenshot task did not produce visual evidence")
source_after = file_sha256(source_file)
if source_after != source_before:
    fail("source scene changed during candidate staging")
receipt = {
    "schema_id": "generated-mesh-stage-receipt/1",
    "request_sha256": request["request_sha256"],
    "admission_receipt_sha256": admission["receipt_sha256"],
    "status": "reconciled" if reconciled else "staged",
    "candidate_scene_path": candidate_path,
    "actor_label": label,
    "static_mesh_path": admission["static_mesh_path"],
    "actor_location": [location.x, location.y, location.z],
    "actor_scale": [scale, scale, scale],
    "result_longest_extent_cm": max(bounds.x, bounds.y, bounds.z) * 2.0 * scale,
    "screenshot_sha256": file_sha256(screenshot),
    "source_scene_sha256_before": source_before,
    "source_scene_sha256_after": source_after,
    "duplicate_side_effect_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
receipt["receipt_sha256"] = hashlib.sha256(
    json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
(evidence_root / "stage-receipt.json").write_text(
    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
unreal.log(f"ARTFLOW_GENERATED_MESH_STAGE status={receipt['status']}")
