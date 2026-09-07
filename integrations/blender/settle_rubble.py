from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import bpy


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


request_path, output_dir, source_blend = (Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1 :])
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-blender-set-dressing-request/1" or sha256(source_blend) != request["source_blend_sha256"]:
    raise RuntimeError("ARTFLOW_SET_DRESSING_FAILED: invalid request or source identity")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(source_blend))
prototype = bpy.data.objects.get(request["prototype"])
surface = bpy.data.objects.get("AF_ShrineCourtyard_Baked")
if prototype is None or surface is None or prototype.type != "MESH" or surface.type != "MESH":
    raise RuntimeError("ARTFLOW_SET_DRESSING_FAILED: registered prototype or surface missing")

collection = bpy.data.collections.new("ArtFlow_SettledRubble")
bpy.context.scene.collection.children.link(collection)
randomizer = random.Random(request["seed"])
low, high = request["bounds"]["min_m"], request["bounds"]["max_m"]
instances = []
for index in range(request["object_count"]):
    obj = prototype.copy()
    obj.data = prototype.data.copy()
    obj.name = f"AF_Settled_Rubble_{index + 1:02d}"
    angle = (index / request["object_count"]) * math.tau + randomizer.uniform(-0.18, 0.18)
    radius = randomizer.uniform(2.8, 4.35)
    obj.location = (math.cos(angle) * radius, math.sin(angle) * radius, randomizer.uniform(1.4, 3.4))
    obj.rotation_euler = tuple(randomizer.uniform(-math.pi, math.pi) for _ in range(3))
    scale = randomizer.uniform(0.8, 1.35)
    obj.scale = (scale, scale, scale)
    obj.hide_render = False
    obj["artflow_set_dressing_request_sha256"] = request["request_sha256"]
    collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.rigidbody.object_add()
    obj.rigid_body.mass = 1.5
    obj.rigid_body.collision_shape = "CONVEX_HULL"
    obj.rigid_body.friction = 0.72
    obj.rigid_body.restitution = 0.08
    obj.select_set(False)
    instances.append(obj)

# The baked courtyard and four invisible walls form the finite simulation volume.
bpy.context.view_layer.objects.active = surface
surface.select_set(True)
bpy.ops.rigidbody.object_add()
surface.rigid_body.type = "PASSIVE"
surface.rigid_body.collision_shape = "MESH"
surface.select_set(False)
bpy.ops.mesh.primitive_cube_add(location=(0, 0, -0.3), scale=(5.0, 5.0, 0.25))
floor = bpy.context.object
floor.name = "AF_SettleFloor"
bpy.ops.rigidbody.object_add()
floor.rigid_body.type = "PASSIVE"
floor.hide_render = True
for location, scale in (
    ((low[0] - 0.1, 0, 1.8), (0.1, 5.0, 2.0)),
    ((high[0] + 0.1, 0, 1.8), (0.1, 5.0, 2.0)),
    ((0, low[1] - 0.1, 1.8), (5.0, 0.1, 2.0)),
    ((0, high[1] + 0.1, 1.8), (5.0, 0.1, 2.0)),
):
    bpy.ops.mesh.primitive_cube_add(location=location, scale=scale)
    wall = bpy.context.object
    wall.name = "AF_SettleBoundary"
    bpy.ops.rigidbody.object_add()
    wall.rigid_body.type = "PASSIVE"
    wall.hide_render = True

scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = request["frame_end"]
for frame in range(scene.frame_start, request["frame_end"]):
    scene.frame_set(frame)
previous = {obj.name: obj.matrix_world.translation.copy() for obj in instances}
scene.frame_set(request["frame_end"])
motions = [(obj.matrix_world.translation - previous[obj.name]).length for obj in instances]
transforms = []
for index, obj in enumerate(instances, start=1):
    solved_matrix = obj.matrix_world.copy()
    loc = solved_matrix.translation.copy()
    rotation = solved_matrix.to_euler("XYZ")
    transforms.append({
        "instance_id": f"rubble-{index:02d}",
        "location_m": [round(loc.x, 6), round(loc.y, 6), round(max(0.0, loc.z), 6)],
        "rotation_deg": [round(math.degrees(value), 4) for value in rotation],
        "scale": [round(value, 5) for value in obj.scale],
    })
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.rigidbody.object_remove()
    obj.matrix_world = solved_matrix
    obj.select_set(False)

minimum = min(
    math.dist(a["location_m"], b["location_m"])
    for index, a in enumerate(transforms)
    for b in transforms[index + 1 :]
)
manifest = {
    "schema_id": "artflow-set-dressing-transform-manifest/1",
    "request_sha256": request["request_sha256"],
    "coordinate_system": "blender-meters-z-up",
    "prototype": request["prototype"],
    "transforms": transforms,
}
manifest["manifest_sha256"] = canonical(manifest)
manifest_path = output_dir / f"{request['output_stem']}-transforms.json"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Export only the registered prototype; Unreal applies the verified transform manifest.
export_object = prototype.copy()
export_object.data = prototype.data.copy()
export_object.data.materials.clear()
export_object.name = "AF_Rubble_Prototype"
export_object.location = (0, 0, 0)
export_object.rotation_euler = (0, 0, 0)
export_object.scale = (1, 1, 1)
collection.objects.link(export_object)
bpy.ops.object.select_all(action="DESELECT")
export_object.select_set(True)
bpy.context.view_layer.objects.active = export_object
prototype_path = output_dir / "AF_Rubble_Prototype.glb"
bpy.ops.export_scene.gltf(filepath=str(prototype_path), export_format="GLB", use_selection=True, export_apply=True)
bpy.data.objects.remove(export_object, do_unlink=True)

scene.camera = bpy.data.objects.get("ArtFlow_Shot_Camera")
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0.65
preview_path = output_dir / f"{request['output_stem']}-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)
blend_path = output_dir / f"{request['output_stem']}.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

artifacts = []
for kind, path in (("blend", blend_path), ("preview", preview_path), ("prototype_glb", prototype_path), ("transform_manifest", manifest_path)):
    artifacts.append({"kind": kind, "relative_path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size})
payload = {
    "schema_id": "artflow-blender-set-dressing-receipt/1",
    "request_id": request["request_id"], "request_sha256": request["request_sha256"],
    "capability_id": request["capability_id"], "status": "succeeded",
    "blender_version": bpy.app.version_string, "instance_count": len(transforms),
    "settled_frame": request["frame_end"], "max_final_motion_m": round(max(motions), 6),
    "min_center_separation_m": round(minimum, 6), "transforms": transforms,
    "artifacts": artifacts, "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "set-dressing-receipt.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"ARTFLOW_SET_DRESSING_SUCCEEDED request={request['request_id']}")
