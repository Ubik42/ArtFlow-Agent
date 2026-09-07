from __future__ import annotations

import hashlib
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import bpy
import bmesh
from mathutils import Vector


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ARTFLOW_CLOTH_BANNER_FAILED: {message}")


def artifact(kind: str, path: Path, root: Path) -> dict[str, object]:
    return {"kind": kind, "relative_path": path.relative_to(root).as_posix(), "sha256": sha256(path), "size_bytes": path.stat().st_size}


def select_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


argv = sys.argv[sys.argv.index("--") + 1 :]
if len(argv) != 2:
    fail("expected request and output directory")
request_path, output_dir = (Path(value).resolve() for value in argv)
request = json.loads(request_path.read_text(encoding="utf-8"))
texture_receipt_path = output_dir / "comfy-banner-texture-receipt.json"
texture_receipt = json.loads(texture_receipt_path.read_text(encoding="utf-8"))
texture_path = output_dir / texture_receipt["texture_path"]
if request.get("schema_id") != "artflow-cloth-banner-request/1":
    fail("unsupported request")
if texture_receipt.get("request_sha256") != request.get("request_sha256"):
    fail("Comfy receipt belongs to another request")
if sha256(texture_path) != texture_receipt.get("texture_sha256"):
    fail("banner texture identity changed")

started = time.perf_counter()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.frame_start = 1
scene.frame_end = request["frame_end"]
scene.render.fps = 24
scene.gravity = (0.0, 0.0, -9.81)

width = request["width_m"]
height = request["height_m"]
columns = request["mesh_columns"]
rows = request["mesh_rows"]
mesh = bpy.data.meshes.new("AF_ClothBanner_EditableMesh")
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=columns, y_segments=rows, size=1.0)
bm.to_mesh(mesh)
bm.free()
banner = bpy.data.objects.new("SM_AF_ClothBanner_Editable", mesh)
scene.collection.objects.link(banner)
for vertex in mesh.vertices:
    x = vertex.co.x * width
    z = (vertex.co.y - 0.5) * height
    vertex.co = (x, 0.0, z)
banner.location = (0.0, 0.0, height)
banner["artflow_request_sha256"] = request["request_sha256"]
banner["artflow_attachment_actor"] = request["attachment_actor"]
banner["artflow_attachment_location_cm"] = request["attachment_location_cm"]

pin = banner.vertex_groups.new(name="AF_PinTop")
top_indices = [vertex.index for vertex in mesh.vertices if vertex.co.z >= height * 0.49]
pin.add(top_indices, 1.0, "REPLACE")
if len(top_indices) != columns + 1:
    fail(f"unexpected pin vertex count: {len(top_indices)}/{columns + 1}")

uv = mesh.uv_layers.new(name="ArtFlow_BannerUV")
for loop in mesh.loops:
    co = mesh.vertices[loop.vertex_index].co
    uv.data[loop.index].uv = ((co.x / width) + 0.5, (co.z / height) + 0.5)

image = bpy.data.images.load(str(texture_path), check_existing=False)
image.name = "T_AF_BannerPattern"
image.pack()
material = bpy.data.materials.new("M_AF_SceneBanner")
material.use_nodes = True
nodes = material.node_tree.nodes
links = material.node_tree.links
bsdf = nodes.get("Principled BSDF")
texture = nodes.new("ShaderNodeTexImage")
texture.name = "ArtFlow_ComfyPattern"
texture.image = image
ramp = nodes.new("ShaderNodeValToRGB")
ramp.name = "ArtFlow_HeraldicPalette"
ramp.color_ramp.elements[0].color = (0.025, 0.055, 0.07, 1.0)
ramp.color_ramp.elements[0].position = 0.24
ramp.color_ramp.elements[1].color = (0.72, 0.28, 0.055, 1.0)
ramp.color_ramp.elements[1].position = 0.7
bump = nodes.new("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.18
bump.inputs["Distance"].default_value = 0.035
links.new(texture.outputs["Color"], ramp.inputs["Fac"])
links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
links.new(texture.outputs["Color"], bump.inputs["Height"])
links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
bsdf.inputs["Roughness"].default_value = 0.82
banner.data.materials.append(material)

select_only(banner)
cloth = banner.modifiers.new("ArtFlow Cloth", "CLOTH")
cloth.settings.quality = 8
cloth.settings.mass = 0.32
cloth.settings.air_damping = 3.0
cloth.settings.tension_stiffness = 22.0
cloth.settings.compression_stiffness = 18.0
cloth.settings.shear_stiffness = 12.0
cloth.settings.bending_stiffness = 0.7
cloth.settings.vertex_group_mass = pin.name
cloth.settings.pin_stiffness = 1.0

bpy.ops.object.effector_add(type="WIND", location=(-3.0, -2.0, height * 0.9))
wind = bpy.context.object
wind.name = "AF_SceneWind"
direction = Vector(request["wind_direction"])
wind.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
wind.field.strength = request["wind_strength"]
wind.field.noise = 1.25

for frame in range(1, request["frame_end"] + 1):
    scene.frame_set(frame)
depsgraph = bpy.context.evaluated_depsgraph_get()
evaluated = banner.evaluated_get(depsgraph)
export_mesh = bpy.data.meshes.new_from_object(evaluated, depsgraph=depsgraph)
export_obj = bpy.data.objects.new("SM_AF_ClothBanner_Baked", export_mesh)
scene.collection.objects.link(export_obj)
export_obj.matrix_world = banner.matrix_world.copy()
if len(export_obj.data.materials) == 0:
    export_obj.data.materials.append(material)
solidify = export_obj.modifiers.new("ArtFlow Fabric Thickness", "SOLIDIFY")
solidify.thickness = 0.012
solidify.offset = 0.0
select_only(export_obj)
bpy.context.view_layer.objects.active = export_obj
bpy.ops.object.modifier_apply(modifier=solidify.name)
export_obj.data.calc_loop_triangles()
triangle_count = len(export_obj.data.loop_triangles)
if triangle_count > request["triangle_budget"]:
    fail(f"banner exceeds triangle budget: {triangle_count}/{request['triangle_budget']}")

glb_path = output_dir / "SM_AF_ClothBanner.glb"
select_only(export_obj)
bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT")

manifest = {
    "schema_id": "artflow-cloth-banner-manifest/1",
    "request_sha256": request["request_sha256"],
    "editable_object": banner.name,
    "export_object": export_obj.name,
    "attachment_actor": request["attachment_actor"],
    "attachment_location_cm": request["attachment_location_cm"],
    "pin_group": pin.name,
    "pin_vertex_count": len(top_indices),
    "cloth_modifier": cloth.name,
    "simulation_frame": request["frame_end"],
    "wind_object": wind.name,
    "uv_layer": export_obj.data.uv_layers.active.name if export_obj.data.uv_layers.active else "",
    "material": material.name,
    "texture_sha256": sha256(texture_path),
    "triangle_count": triangle_count,
    "glb_sha256": sha256(glb_path),
}
manifest["manifest_sha256"] = canonical(manifest)
manifest_path = output_dir / "AF_ClothBanner-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

banner.hide_render = True
wind.hide_render = True
bpy.ops.mesh.primitive_plane_add(size=18, location=(0, 0, -0.03))
ground = bpy.context.object
ground_material = bpy.data.materials.new("M_AF_BannerGround")
ground_material.diffuse_color = (0.018, 0.025, 0.032, 1)
ground.data.materials.append(ground_material)
bpy.ops.object.camera_add(location=(7.5, -12.5, 5.3))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 0, 2.5)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.lens = 58
scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(-4.0, -4.5, 8.0))
key = bpy.context.object
key.data.energy = 1350
key.data.size = 5.0
key.rotation_euler = (Vector((0, 0, 2.4)) - key.location).to_track_quat("-Z", "Y").to_euler()
bpy.ops.object.light_add(type="AREA", location=(4.0, -1.0, 4.5))
fill = bpy.context.object
fill.data.energy = 750
fill.data.color = (0.2, 0.5, 1.0)
fill.rotation_euler = (Vector((0, 0, 2.4)) - fill.location).to_track_quat("-Z", "Y").to_euler()
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.world = bpy.data.worlds.new("AF_BannerWorld")
scene.world.color = (0.004, 0.008, 0.014)
preview_path = output_dir / "AF_ClothBanner-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)

blend_path = output_dir / "AF_ClothBanner.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
artifacts = [artifact("blend", blend_path, output_dir), artifact("glb", glb_path, output_dir), artifact("manifest", manifest_path, output_dir), artifact("texture", texture_path, output_dir), artifact("preview", preview_path, output_dir)]
receipt = {
    "schema_id": "artflow-blender-cloth-banner-receipt/1",
    "request_sha256": request["request_sha256"],
    "comfy_receipt_sha256": texture_receipt["receipt_sha256"],
    "capability_id": request["blender_capability_id"],
    "status": "succeeded",
    "blender_version": bpy.app.version_string,
    "editable_object": banner.name,
    "export_object": export_obj.name,
    "pin_group": pin.name,
    "pin_vertex_count": len(top_indices),
    "simulation_frame": request["frame_end"],
    "triangle_count": triangle_count,
    "uv_layer": manifest["uv_layer"],
    "material": material.name,
    "artifacts": artifacts,
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
receipt["receipt_sha256"] = canonical(receipt)
(output_dir / "blender-cloth-banner-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print("ARTFLOW_CLOTH_BANNER_OK=" + receipt["receipt_sha256"])
