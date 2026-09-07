from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import bpy


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ARTFLOW_SURFACE_FAILED: {message}")


request_path, output_dir, source_blend = (
    Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1 :]
)
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-blender-surface-request/1":
    fail("unsupported request")
if sha256(source_blend) != request["source_blend_sha256"]:
    fail("source blend identity mismatch")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(source_blend))
depsgraph = bpy.context.evaluated_depsgraph_get()
surface_collection = bpy.data.collections.new("ArtFlow_BakedSurface")
bpy.context.scene.collection.children.link(surface_collection)
parts = []
for item in request["objects"]:
    source = bpy.data.objects.get(item["name"])
    if source is None or source.type != "MESH" or not source.get("artflow_generated"):
        fail(f"registered mesh is missing: {item['name']}")
    if item["source"] == "geometry_nodes_output":
        evaluated = source.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
        part = bpy.data.objects.new(f"{source.name}_Surface", mesh)
        part.matrix_world = source.matrix_world.copy()
    else:
        part = source.copy()
        part.data = source.data.copy()
        part.animation_data_clear()
    surface_collection.objects.link(part)
    parts.append(part)

bpy.ops.object.select_all(action="DESELECT")
for part in parts:
    part.select_set(True)
bpy.context.view_layer.objects.active = parts[0]
bpy.ops.object.join()
surface = bpy.context.view_layer.objects.active
surface.name = request["output_stem"]
surface.data.name = f"{request['output_stem']}_Mesh"
surface["artflow_generated"] = True
surface["artflow_surface_request_sha256"] = request["request_sha256"]
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

if len(surface.data.vertices) > request["max_vertices"]:
    fail("vertex budget exceeded")
surface.data.calc_loop_triangles()
if len(surface.data.loop_triangles) > request["max_triangles"]:
    fail("triangle budget exceeded")

while surface.data.uv_layers:
    surface.data.uv_layers.remove(surface.data.uv_layers[0])
uv_layer = surface.data.uv_layers.new(name=request["uv_set"], do_init=False)
surface.data.uv_layers.active = uv_layer
bpy.context.view_layer.objects.active = surface
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(
    angle_limit=math.radians(66.0),
    island_margin=request["margin_px"] / request["atlas_resolution"],
)
bpy.ops.object.mode_set(mode="OBJECT")

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 1
scene.render.bake.use_clear = True
scene.render.bake.margin = request["margin_px"]
resolution = request["atlas_resolution"]


def make_target(name: str, color: tuple[float, float, float, float]):
    image = bpy.data.images.new(name, width=resolution, height=resolution, alpha=False)
    image.generated_color = color
    for material in {slot.material for slot in surface.material_slots if slot.material}:
        if not material.use_nodes:
            material.use_nodes = True
        nodes = material.node_tree.nodes
        for node in nodes:
            node.select = False
        target = nodes.new("ShaderNodeTexImage")
        target.name = f"ArtFlow_{name}_BakeTarget"
        target.image = image
        target.select = True
        nodes.active = target
    return image


base_image = make_target("BaseColor", (0.18, 0.18, 0.18, 1.0))
bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"})
base_path = output_dir / f"{request['output_stem']}_BaseColor.png"
base_image.filepath_raw = str(base_path)
base_image.file_format = "PNG"
base_image.save()

rough_image = make_target("Roughness", (0.72, 0.72, 0.72, 1.0))
bpy.ops.object.bake(type="ROUGHNESS")
rough_path = output_dir / f"{request['output_stem']}_Roughness.png"
rough_image.filepath_raw = str(rough_path)
rough_image.file_format = "PNG"
rough_image.colorspace_settings.name = "Non-Color"
rough_image.save()

baked_material = bpy.data.materials.new("M_AF_BakedSurface")
baked_material.use_nodes = True
nodes = baked_material.node_tree.nodes
links = baked_material.node_tree.links
bsdf = nodes.get("Principled BSDF")
base_node = nodes.new("ShaderNodeTexImage")
base_node.name = "ArtFlow_BaseColor"
base_node.image = base_image
rough_node = nodes.new("ShaderNodeTexImage")
rough_node.name = "ArtFlow_Roughness"
rough_node.image = rough_image
rough_node.image.colorspace_settings.name = "Non-Color"
links.new(base_node.outputs["Color"], bsdf.inputs["Base Color"])
links.new(rough_node.outputs["Color"], bsdf.inputs["Roughness"])
baked_material["artflow_surface_request_sha256"] = request["request_sha256"]
surface.data.materials.clear()
surface.data.materials.append(baked_material)
for polygon in surface.data.polygons:
    polygon.material_index = 0

base_image.pack()
rough_image.pack()
bpy.ops.object.select_all(action="DESELECT")
surface.select_set(True)
bpy.context.view_layer.objects.active = surface
glb_path = output_dir / f"{request['output_stem']}.glb"
bpy.ops.export_scene.gltf(
    filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True
)

for obj in bpy.context.scene.objects:
    if obj.type == "MESH" and obj is not surface:
        obj.hide_render = True
camera = bpy.data.objects.get("ArtFlow_Shot_Camera")
if camera is None:
    fail("registered camera is missing")
scene.camera = camera
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0.65
preview_path = output_dir / f"{request['output_stem']}-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)
blend_path = output_dir / f"{request['output_stem']}.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

surface.data.calc_loop_triangles()
uv_data = surface.data.uv_layers[request["uv_set"]].data
uv_area = 0.0
for triangle in surface.data.loop_triangles:
    points = [uv_data[index].uv for index in triangle.loops]
    uv_area += abs(
        (points[1].x - points[0].x) * (points[2].y - points[0].y)
        - (points[2].x - points[0].x) * (points[1].y - points[0].y)
    ) * 0.5

artifacts = []
for kind, path in (
    ("blend", blend_path), ("glb", glb_path), ("preview", preview_path),
    ("base_color", base_path), ("roughness", rough_path),
):
    artifacts.append({
        "kind": kind,
        "relative_path": path.name,
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    })
payload = {
    "schema_id": "artflow-blender-surface-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "capability_id": request["capability_id"],
    "status": "succeeded",
    "blender_version": bpy.app.version_string,
    "object_name": surface.name,
    "source_object_count": len(request["objects"]),
    "vertex_count": len(surface.data.vertices),
    "triangle_count": len(surface.data.loop_triangles),
    "uv_set": request["uv_set"],
    "uv_loop_count": len(uv_data),
    "uv_area_ratio": round(min(1.0, uv_area), 6),
    "atlas_resolution": resolution,
    "material_slots": [slot.material.name for slot in surface.material_slots],
    "artifacts": artifacts,
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "surface-receipt.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"ARTFLOW_SURFACE_SUCCEEDED request={request['request_id']}")
