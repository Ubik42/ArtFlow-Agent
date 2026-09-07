from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import unreal


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow spline infrastructure failed: {message}")


def add_spline_component(actor: unreal.Actor, name: str) -> unreal.SplineComponent:
    subsystem = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    actor_handle = None
    root_handle = None
    for handle in subsystem.k2_gather_subobject_data_for_instance(actor):
        data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(handle)
        if unreal.SubobjectDataBlueprintFunctionLibrary.is_actor(data):
            actor_handle = handle
        elif unreal.SubobjectDataBlueprintFunctionLibrary.is_root_component(data):
            root_handle = handle
    if actor_handle is None:
        fail(f"could not resolve actor subobject for {name}")
    if root_handle is None:
        root_handle, error = subsystem.add_new_subobject(
            unreal.AddNewSubobjectParams(
                parent_handle=actor_handle,
                new_class=unreal.SceneComponent.static_class(),
                blueprint_context=None,
            )
        )
        if not error.is_empty():
            fail(str(error))
        subsystem.rename_subobject(handle=root_handle, new_name=unreal.Text("DefaultSceneRoot"))
    spline_handle, error = subsystem.add_new_subobject(
        unreal.AddNewSubobjectParams(
            parent_handle=root_handle,
            new_class=unreal.SplineComponent.static_class(),
            blueprint_context=None,
        )
    )
    if not error.is_empty():
        fail(str(error))
    subsystem.rename_subobject(handle=spline_handle, new_name=unreal.Text(name))
    data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(spline_handle)
    component = unreal.SubobjectDataBlueprintFunctionLibrary.get_associated_object(data)
    if not isinstance(component, unreal.SplineComponent):
        fail(f"could not create spline component for {name}")
    return component


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m49-s1-spline-infrastructure"
request = json.loads((evidence / "spline-infrastructure-request.json").read_text(encoding="utf-8"))
corridor = json.loads((evidence / "comfy-route-corridor-receipt.json").read_text(encoding="utf-8"))
blender = json.loads(
    (evidence / "blender-spline-infrastructure-receipt.json").read_text(encoding="utf-8")
)
manifest_path = evidence / next(
    item["relative_path"] for item in blender["artifacts"] if item["kind"] == "manifest"
)
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if (
    corridor["request_sha256"] != request["request_sha256"]
    or blender["request_sha256"] != request["request_sha256"]
):
    fail("receipt chain differs from the request")
for item in blender["artifacts"]:
    if sha256(evidence / item["relative_path"]) != item["sha256"]:
        fail(f"Blender artifact identity drifted: {item['relative_path']}")

project = Path(unreal.Paths.project_dir()).resolve()
source_file = (
    project / "Content" / (request["source_candidate_scene_path"].removeprefix("/Game/") + ".umap")
)
source_before = sha256(source_file)
if source_before != request["source_candidate_sha256"]:
    fail("source modular candidate changed after request compilation")

identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Blender/Spline/S_{identity}"
asset_specs = {
    "segment": next(item for item in blender["artifacts"] if item["kind"] == "segment_glb"),
    "support": next(item for item in blender["artifacts"] if item["kind"] == "support_glb"),
}
assets = {}
assets_reconciled = True
for kind, item in asset_specs.items():
    tag_value = f"{request['request_sha256']}:{kind}"
    mesh = None
    for path in unreal.EditorAssetLibrary.list_assets(
        destination, recursive=True, include_folder=False
    ):
        candidate = unreal.EditorAssetLibrary.load_asset(path)
        if (
            isinstance(candidate, unreal.StaticMesh)
            and unreal.EditorAssetLibrary.get_metadata_tag(candidate, "ArtFlow.SplineAsset")
            == tag_value
        ):
            mesh = candidate
            break
    if mesh is None:
        assets_reconciled = False
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(evidence / item["relative_path"]))
        task.set_editor_property("destination_path", destination)
        task.set_editor_property("destination_name", f"SM_AF_Spline{kind.title()}")
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
        fail(f"Interchange did not produce {kind} mesh")
    unreal.EditorAssetLibrary.set_metadata_tag(mesh, "ArtFlow.SplineAsset", tag_value)
    if unreal.EditorStaticMeshLibrary.get_convex_collision_count(mesh) == 0:
        unreal.EditorStaticMeshLibrary.add_simple_collisions(
            mesh, unreal.ScriptingCollisionShapeType.BOX
        )
    unreal.EditorAssetLibrary.save_loaded_asset(mesh, only_if_is_dirty=False)
    assets[kind] = mesh

candidate_name = f"Spline_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    candidate = unreal.EditorAssetLibrary.duplicate_asset(
        request["source_candidate_scene_path"], candidate_package
    )
    if candidate is None:
        fail("could not derive spline infrastructure candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()

world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = subsystem.get_all_level_actors()
created = 0
spline_records = []
segment_records = []
support_records = []
for route in manifest["routes"]:
    route_label = f"ArtFlow_Spline_{route['route_id']}"
    actor = next((value for value in actors if value.get_actor_label() == route_label), None)
    if actor is None:
        actor = subsystem.spawn_actor_from_class(
            unreal.Actor,
            unreal.Vector(0, 0, 0),
            unreal.Rotator(roll=0, pitch=0, yaw=0),
        )
        actor.set_actor_label(route_label)
        created += 1
    components = actor.get_components_by_class(unreal.SplineComponent)
    spline = (
        components[0] if components else add_spline_component(actor, f"Spline_{route['route_id']}")
    )
    if not isinstance(spline, unreal.SplineComponent):
        fail(f"could not create spline component for {route['route_id']}")
    points = [unreal.Vector(*point) for point in route["control_points_cm"]]
    spline.set_spline_points(points, unreal.SplineCoordinateSpace.WORLD, True)
    actor.tags = ["ArtFlow.Spline", request["request_id"], route["route_id"], route["kind"]]
    spline_records.append(
        {
            "route_id": route["route_id"],
            "actor_label": route_label,
            "component_name": spline.get_name(),
            "control_point_count": len(points),
        }
    )
    for index, (start, end) in enumerate(pairwise(points), start=1):
        label = f"ArtFlow_SplineSegment_{route['route_id']}_{index:02d}"
        segment_actor = next((value for value in actors if value.get_actor_label() == label), None)
        delta = end - start
        length_cm = delta.length()
        midpoint = (start + end) * 0.5
        yaw = math.degrees(math.atan2(delta.y, delta.x))
        if segment_actor is None:
            segment_actor = subsystem.spawn_actor_from_object(
                assets["segment"], midpoint, unreal.Rotator(roll=0, pitch=0, yaw=yaw)
            )
            segment_actor.set_actor_label(label)
            created += 1
        segment_actor.set_actor_location(midpoint, False, False)
        segment_actor.set_actor_rotation(unreal.Rotator(roll=0, pitch=0, yaw=yaw), False)
        segment_actor.set_actor_scale3d(
            unreal.Vector(
                length_cm / 100.0, route["diameter_cm"] / 18.0, route["diameter_cm"] / 18.0
            )
        )
        segment_actor.tags = ["ArtFlow.SplineSegment", request["request_id"], route["route_id"]]
        segment_records.append(
            {"actor_label": label, "route_id": route["route_id"], "length_cm": round(length_cm, 3)}
        )

for item in manifest["supports"]:
    label = f"ArtFlow_SplineSupport_{item['support_id']}"
    actor = next((value for value in actors if value.get_actor_label() == label), None)
    if actor is None:
        actor = subsystem.spawn_actor_from_object(
            assets["support"],
            unreal.Vector(*item["location_cm"]),
            unreal.Rotator(roll=0, pitch=0, yaw=0),
        )
        actor.set_actor_label(label)
        created += 1
    actor.tags = ["ArtFlow.SplineSupport", request["request_id"], item["route_id"]]
    support_records.append(
        {"support_id": item["support_id"], "actor_label": label, "route_id": item["route_id"]}
    )

unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
screenshot = evidence / "unreal-spline-infrastructure-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
camera_label = "ArtFlow_Spline_Camera"
camera = next((actor for actor in actors if actor.get_actor_label() == camera_label), None)
if camera is None:
    camera = subsystem.spawn_actor_from_class(
        unreal.CameraActor,
        unreal.Vector(0, -850, 900),
        unreal.Rotator(roll=0, pitch=0, yaw=0),
    )
    camera.set_actor_label(camera_label)
    created += 1
camera.set_actor_location(unreal.Vector(0, -850, 900), False, False)
camera.set_actor_rotation(
    unreal.MathLibrary.find_look_at_rotation(
        unreal.Vector(0, -850, 900), unreal.Vector(0, 300, 150)
    ),
    False,
)
camera.get_editor_property("camera_component").set_editor_property("field_of_view", 55.0)
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
state = {"ticks": 0, "callback": None}


def finish():
    unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)
    source_after = sha256(source_file)
    if source_after != source_before:
        fail("spline route changed the upstream modular candidate")
    current_actors = subsystem.get_all_level_actors()
    labels = {actor.get_actor_label() for actor in current_actors}
    expected = {item["actor_label"] for item in spline_records + segment_records + support_records}
    if not expected <= labels:
        fail("not every registered spline actor exists")
    result = {
        "schema_id": "artflow-unreal-spline-infrastructure-receipt/1",
        "request_sha256": request["request_sha256"],
        "corridor_receipt_sha256": corridor["receipt_sha256"],
        "blender_receipt_sha256": blender["receipt_sha256"],
        "status": "reconciled"
        if assets_reconciled and candidate_reconciled and created == 0
        else "generated",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "source_candidate_scene_path": request["source_candidate_scene_path"],
        "candidate_scene_path": candidate_package,
        "mesh_paths": {key: value.get_path_name() for key, value in assets.items()},
        "spline_component_count": len(spline_records),
        "control_point_count": sum(item["control_point_count"] for item in spline_records),
        "segment_actor_count": len(segment_records),
        "support_actor_count": len(support_records),
        "created_actor_count": created,
        "duplicate_side_effect_count": 0,
        "splines": spline_records,
        "segments": segment_records,
        "supports": support_records,
        "source_candidate_sha256_before": source_before,
        "source_candidate_sha256_after": source_after,
        "screenshot_path": screenshot.name,
        "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
        "capture_status": "captured" if screenshot.is_file() else "unavailable",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-spline-infrastructure-receipt.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    unreal.log(
        f"ARTFLOW_SPLINE_RETURN status={result['status']} splines={len(spline_records)} segments={len(segment_records)} supports={len(support_records)}"
    )
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta):
    state["ticks"] += 1
    if state["ticks"] == 2 and isinstance(camera, unreal.CameraActor):
        unreal.AutomationLibrary.take_high_res_screenshot(
            1280, 720, str(screenshot), camera, False, False
        )
    if screenshot.is_file() or state["ticks"] > 240:
        finish()


state["callback"] = unreal.register_slate_post_tick_callback(on_tick)
