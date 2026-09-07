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
from mathutils import Vector


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(kind: str, path: Path, root: Path) -> dict[str, object]:
    return {
        "kind": kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


def mesh_object(
    name: str,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    collection: bpy.types.Collection,
    material: bpy.types.Material,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


argv = sys.argv[sys.argv.index("--") + 1 :]
if len(argv) != 3:
    raise RuntimeError("ARTFLOW_BLENDER_LAYOUT_FAILED: expected request, output and source blend")
request_path, output_dir, source_blend = (Path(value).resolve() for value in argv)
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-blender-geometry-layout-request/1":
    raise RuntimeError("ARTFLOW_BLENDER_LAYOUT_FAILED: unsupported request")
if sha256(source_blend) != request["source_blend_sha256"]:
    raise RuntimeError("ARTFLOW_BLENDER_LAYOUT_FAILED: source blend identity mismatch")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(source_blend))
stone = bpy.data.materials.get("M_AF_Stone")
weathering = bpy.data.materials.get("M_AF_Weathering")
gold = bpy.data.materials.get("M_AF_Inlay")
if stone is None or weathering is None or gold is None:
    raise RuntimeError("ARTFLOW_BLENDER_LAYOUT_FAILED: declared material targets are missing")

prototype_collection = bpy.data.collections.new("AF_GN_Courtyard_Prototypes")
slab = mesh_object(
    "AF_Proto_Slab",
    [(-0.55, -0.25, 0), (0.55, -0.25, 0), (0.55, 0.25, 0), (-0.55, 0.25, 0),
     (-0.55, -0.25, 0.18), (0.55, -0.25, 0.18), (0.55, 0.25, 0.18), (-0.55, 0.25, 0.18)],
    [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (4, 0, 3, 7)],
    prototype_collection,
    stone,
)
obelisk = mesh_object(
    "AF_Proto_Obelisk",
    [(-0.22, -0.22, 0), (0.22, -0.22, 0), (0.22, 0.22, 0), (-0.22, 0.22, 0),
     (-0.14, -0.14, 1.25), (0.14, -0.14, 1.25), (0.14, 0.14, 1.25), (-0.14, 0.14, 1.25), (0, 0, 1.58)],
    [(0, 1, 2, 3), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0),
     (4, 8, 5), (5, 8, 6), (6, 8, 7), (7, 8, 4)],
    prototype_collection,
    weathering,
)
rubble = mesh_object(
    "AF_Proto_Rubble",
    [(0, 0, 0.52), (0, 0, -0.08), (0.42, 0, 0.18), (-0.35, 0, 0.16), (0, 0.32, 0.2), (0, -0.38, 0.17)],
    [(0, 2, 4), (0, 4, 3), (0, 3, 5), (0, 5, 2), (1, 4, 2), (1, 3, 4), (1, 5, 3), (1, 2, 5)],
    prototype_collection,
    gold,
)
for index, prototype in enumerate((slab, obelisk, rubble)):
    prototype.scale.z *= 1.0 + request["height_variation"] * (index - 1)

rng = random.Random(request["seed"])
radius = request["radius_cm"] / 100.0
points: list[tuple[float, float, float]] = []
for index in range(request["support_count"]):
    angle = math.tau * index / request["support_count"] + rng.uniform(-0.11, 0.11)
    distance = radius * rng.uniform(0.78, 1.0)
    points.append((math.cos(angle) * distance, math.sin(angle) * distance, rng.uniform(0.0, 0.08)))

carrier_mesh = bpy.data.meshes.new("AF_GN_Courtyard_Points")
carrier_mesh.from_pydata(points, [], [])
carrier = bpy.data.objects.new("AF_GN_ShrineCourtyard", carrier_mesh)
bpy.context.scene.collection.objects.link(carrier)
carrier["artflow_generated"] = True
carrier["artflow_capability"] = request["capability_id"]

node_group = bpy.data.node_groups.new("AF_GN_ShrineCourtyard_v1", "GeometryNodeTree")
node_group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
node_group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
nodes = node_group.nodes
links = node_group.links
group_in = nodes.new("NodeGroupInput")
group_out = nodes.new("NodeGroupOutput")
collection_info = nodes.new("GeometryNodeCollectionInfo")
collection_info.inputs["Collection"].default_value = prototype_collection
instance = nodes.new("GeometryNodeInstanceOnPoints")
instance.inputs["Pick Instance"].default_value = True
index_node = nodes.new("GeometryNodeInputIndex")
modulo = nodes.new("ShaderNodeMath")
modulo.operation = "MODULO"
modulo.inputs[1].default_value = 3.0
realize = nodes.new("GeometryNodeRealizeInstances")
links.new(group_in.outputs["Geometry"], instance.inputs["Points"])
links.new(collection_info.outputs["Instances"], instance.inputs["Instance"])
links.new(index_node.outputs["Index"], modulo.inputs[0])
links.new(modulo.outputs[0], instance.inputs["Instance Index"])
links.new(instance.outputs["Instances"], realize.inputs["Geometry"])
links.new(realize.outputs["Geometry"], group_out.inputs["Geometry"])
modifier = carrier.modifiers.new("AF_GN_ShrineCourtyard_v1", "NODES")
modifier.node_group = node_group

stem = request["output_stem"]
blend_path = output_dir / f"{stem}.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

depsgraph = bpy.context.evaluated_depsgraph_get()
evaluated = carrier.evaluated_get(depsgraph)
realized_mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
realized = bpy.data.objects.new("AF_Courtyard_Realized", realized_mesh)
bpy.context.scene.collection.objects.link(realized)
hero_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj.get("artflow_generated") and obj != carrier]
bpy.ops.object.select_all(action="DESELECT")
for obj in hero_objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = hero_objects[0]
bpy.ops.object.duplicate(linked=False)
export_objects = list(bpy.context.selected_objects)
realized.select_set(True)
export_objects.append(realized)
bpy.context.view_layer.objects.active = export_objects[0]
bpy.ops.object.join()
export_mesh = bpy.context.object
export_mesh.name = stem
export_mesh.data.calc_loop_triangles()

minimum = Vector((float("inf"),) * 3)
maximum = Vector((float("-inf"),) * 3)
for corner in export_mesh.bound_box:
    point = export_mesh.matrix_world @ Vector(corner)
    minimum = Vector(tuple(min(a, b) for a, b in zip(minimum, point)))
    maximum = Vector(tuple(max(a, b) for a, b in zip(maximum, point)))
glb_path = output_dir / f"{stem}.glb"
bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True)
bpy.data.objects.remove(export_mesh, do_unlink=True)

camera = bpy.data.objects.get("ArtFlow_Preview_Camera")
if camera:
    camera.location = (10.5, -12.5, 8.2)
    camera.rotation_euler = (Vector((0, 0, 1.0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
scene = bpy.context.scene
scene.render.resolution_x = 1100
scene.render.resolution_y = 760
preview_path = output_dir / f"{stem}-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)

payload = {
    "schema_id": "artflow-blender-geometry-layout-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "capability_id": request["capability_id"],
    "blender_version": bpy.app.version_string,
    "status": "succeeded",
    "node_group": node_group.name,
    "support_element_count": request["support_count"],
    "prototype_count": 3,
    "realized_vertex_count": len(realized_mesh.vertices),
    "realized_triangle_count": len(realized_mesh.loop_triangles),
    "bounds_cm": [round((maximum[i] - minimum[i]) * 100.0, 3) for i in range(3)],
    "artifacts": [artifact("blend", blend_path, output_dir), artifact("glb", glb_path, output_dir), artifact("preview", preview_path, output_dir)],
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
(output_dir / "layout-receipt.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"ARTFLOW_BLENDER_LAYOUT_SUCCEEDED request={request['request_id']} elements={request['support_count']}")
