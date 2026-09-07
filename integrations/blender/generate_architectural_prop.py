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


def fail(message: str) -> None:
    raise RuntimeError(f"ARTFLOW_BLENDER_FAILED: {message}")


def add_box(name: str, location: tuple[float, float, float], scale: tuple[float, float, float], material: bpy.types.Material, bevel: float) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    modifier = obj.modifiers.new("ArtFlow_Bevel", "BEVEL")
    modifier.width = bevel
    modifier.segments = 3
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.data.materials.append(material)
    return obj


def make_material(name: str, color: tuple[float, float, float, float], roughness: float, metallic: float = 0.0) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    node = material.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = color
    node.inputs["Roughness"].default_value = roughness
    node.inputs["Metallic"].default_value = metallic
    return material


def artifact(kind: str, path: Path, root: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "kind": kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


argv = sys.argv[sys.argv.index("--") + 1 :]
if len(argv) != 2:
    fail("expected a request JSON and an output directory")
request_path = Path(argv[0]).resolve()
output_dir = Path(argv[1]).resolve()
request = json.loads(request_path.read_text(encoding="utf-8"))
required = {
    "schema_id", "request_id", "request_sha256", "session_id", "session_sha256",
    "source_scene", "source_level_sha256", "capability_id", "recipe", "width_cm",
    "depth_cm", "height_cm", "tier_count", "pillar_count", "detail_level", "seed",
    "palette", "output_stem",
}
if set(request) != required:
    fail("request fields do not match the registered contract")
if request["schema_id"] != "artflow-blender-modeling-request/1" or request["recipe"] != "weathered_shrine" or request["capability_id"] != "blender.architectural_prop.weathered_shrine.v1":
    fail("request does not select the registered modeling capability")

started = time.perf_counter()
randomizer = random.Random(request["seed"])
bpy.ops.object.select_all(action="SELECT")
bpy.ops.object.delete(use_global=False)
for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
    for datablock in list(datablocks):
        if datablock.users == 0:
            datablocks.remove(datablock)

bpy.context.scene.unit_settings.system = "METRIC"
bpy.context.scene.unit_settings.scale_length = 1.0
palettes = {
    "basalt_moss": ((0.055, 0.07, 0.075, 1), (0.12, 0.24, 0.11, 1), (0.23, 0.14, 0.055, 1)),
    "sandstone_ember": ((0.34, 0.19, 0.09, 1), (0.48, 0.25, 0.07, 1), (0.8, 0.22, 0.035, 1)),
    "limestone_rain": ((0.3, 0.33, 0.34, 1), (0.08, 0.18, 0.15, 1), (0.12, 0.3, 0.38, 1)),
}
stone_color, accent_color, metal_color = palettes[request["palette"]]
stone = make_material("M_AF_Stone", stone_color, 0.78)
accent = make_material("M_AF_Weathering", accent_color, 0.92)
metal = make_material("M_AF_Inlay", metal_color, 0.28, 0.65)

width = request["width_cm"] / 100.0
depth = request["depth_cm"] / 100.0
height = request["height_cm"] / 100.0
objects: list[bpy.types.Object] = []
tier_height = height * 0.055
for tier in range(request["tier_count"]):
    shrink = tier * width * 0.055
    objects.append(add_box(
        f"AF_Base_{tier + 1:02d}",
        (0, 0, tier_height * (tier + 0.5)),
        ((width - shrink) * 0.5, (depth - shrink * 0.7) * 0.5, tier_height * 0.5),
        stone if tier % 2 == 0 else accent,
        0.035,
    ))
base_top = tier_height * request["tier_count"]
pillar_height = height * 0.58
pillar_x = width * 0.34
pillar_y_values = [0.0] if request["pillar_count"] == 2 else [-depth * 0.25, depth * 0.25]
for side in (-1, 1):
    for index, y in enumerate(pillar_y_values):
        objects.append(add_box(
            f"AF_Pillar_{side}_{index}",
            (side * pillar_x, y, base_top + pillar_height * 0.5),
            (width * 0.075, depth * 0.075, pillar_height * 0.5),
            stone,
            0.045,
        ))
cap_z = base_top + pillar_height
objects.append(add_box("AF_Lintel", (0, 0, cap_z), (width * 0.46, depth * 0.12, height * 0.055), stone, 0.045))
objects.append(add_box("AF_Crown", (0, 0, cap_z + height * 0.095), (width * 0.34, depth * 0.16, height * 0.045), accent, 0.035))
objects.append(add_box("AF_Altar", (0, -depth * 0.06, base_top + height * 0.19), (width * 0.19, depth * 0.22, height * 0.18), stone, 0.055))
objects.append(add_box("AF_Inlay", (0, -depth * 0.285, base_top + height * 0.27), (width * 0.105, depth * 0.018, height * 0.105), metal, 0.018))

for index in range(request["detail_level"] * 5):
    angle = randomizer.uniform(0, math.tau)
    radius = randomizer.uniform(width * 0.36, width * 0.52)
    size = randomizer.uniform(width * 0.018, width * 0.045)
    rubble = add_box(
        f"AF_Rubble_{index + 1:02d}",
        (math.cos(angle) * radius, math.sin(angle) * min(radius, depth * 0.44), size * 0.55),
        (size, size * randomizer.uniform(0.55, 1.2), size * randomizer.uniform(0.35, 0.8)),
        accent if index % 3 == 0 else stone,
        size * 0.18,
    )
    rubble.rotation_euler[2] = randomizer.uniform(-0.7, 0.7)
    objects.append(rubble)

for obj in objects:
    obj["artflow_generated"] = True
    obj["artflow_request_sha256"] = request["request_sha256"]
    obj.select_set(True)

bpy.ops.object.select_all(action="DESELECT")
for obj in objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = objects[0]
bpy.ops.object.duplicate(linked=False)
export_objects = list(bpy.context.selected_objects)
bpy.context.view_layer.objects.active = export_objects[0]
bpy.ops.object.join()
export_mesh = bpy.context.object
export_mesh.name = request["output_stem"]
glb_path = output_dir / f"{request['output_stem']}.glb"
bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True)
bpy.data.objects.remove(export_mesh, do_unlink=True)

bpy.ops.object.select_all(action="DESELECT")
camera_data = bpy.data.cameras.new("ArtFlow_Preview_Camera")
camera = bpy.data.objects.new("ArtFlow_Preview_Camera", camera_data)
bpy.context.collection.objects.link(camera)
camera.location = (width * 1.25, -depth * 1.65, height * 0.9)
direction = Vector((0, 0, height * 0.38)) - camera.location
camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = camera
for name, location, energy, size in (
    ("ArtFlow_Key", (width, -depth, height * 1.4), 1200, 4.0),
    ("ArtFlow_Rim", (-width, depth * 0.4, height), 850, 3.0),
):
    light_data = bpy.data.lights.new(name, "AREA")
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size
    light = bpy.data.objects.new(name, light_data)
    bpy.context.collection.objects.link(light)
    light.location = location
    light.rotation_euler = (Vector((0, 0, height * 0.3)) - light.location).to_track_quat("-Z", "Y").to_euler()

scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 960
scene.render.resolution_y = 960
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = str(output_dir / f"{request['output_stem']}-preview.png")
scene.world.color = (0.012, 0.016, 0.022)
scene.render.film_transparent = False
bpy.ops.wm.save_as_mainfile(filepath=str(output_dir / f"{request['output_stem']}.blend"))
bpy.ops.render.render(write_still=True)

vertex_count = 0
triangle_count = 0
minimum = Vector((float("inf"),) * 3)
maximum = Vector((float("-inf"),) * 3)
for obj in objects:
    mesh = obj.data
    mesh.calc_loop_triangles()
    vertex_count += len(mesh.vertices)
    triangle_count += len(mesh.loop_triangles)
    for corner in obj.bound_box:
        point = obj.matrix_world @ Vector(corner)
        minimum = Vector(tuple(min(a, b) for a, b in zip(minimum, point)))
        maximum = Vector(tuple(max(a, b) for a, b in zip(maximum, point)))

blend_path = output_dir / f"{request['output_stem']}.blend"
preview_path = output_dir / f"{request['output_stem']}-preview.png"
payload = {
    "schema_id": "artflow-blender-modeling-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "capability_id": request["capability_id"],
    "blender_version": bpy.app.version_string,
    "status": "succeeded",
    "object_count": len(objects),
    "mesh_count": len(objects),
    "vertex_count": vertex_count,
    "triangle_count": triangle_count,
    "material_count": 3,
    "bounds_cm": [round((maximum[i] - minimum[i]) * 100.0, 3) for i in range(3)],
    "artifacts": [artifact("blend", blend_path, output_dir), artifact("glb", glb_path, output_dir), artifact("preview", preview_path, output_dir)],
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
payload["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
(output_dir / "modeling-receipt.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"ARTFLOW_BLENDER_SUCCEEDED request={request['request_id']} glb={glb_path} triangles={triangle_count}")
