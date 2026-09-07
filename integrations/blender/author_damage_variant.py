from __future__ import annotations

import hashlib
import json
import math
import shutil
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import bpy
from mathutils import Vector


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ARTFLOW_DAMAGE_VARIANT_FAILED: {message}")


def artifact(kind: str, path: Path, root: Path) -> dict[str, object]:
    return {
        "kind": kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


def select_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.hide_viewport = False
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


argv = sys.argv[sys.argv.index("--") + 1 :]
if len(argv) != 2:
    fail("expected request and output directory")
request_path, output_dir = (Path(value).resolve() for value in argv)
request = json.loads(request_path.read_text(encoding="utf-8"))
comfy_path = output_dir / "comfy-damage-field-receipt.json"
comfy = json.loads(comfy_path.read_text(encoding="utf-8"))
source_blend = Path(request["source_blend_path"])
field_path = output_dir / comfy["field_path"]
if request.get("schema_id") != "artflow-damage-variant-request/1":
    fail("unsupported request")
if comfy.get("request_sha256") != request.get("request_sha256"):
    fail("Comfy receipt belongs to another request")
if sha256(field_path) != comfy.get("field_sha256"):
    fail("damage field identity changed")
if sha256(source_blend) != request.get("source_blend_sha256"):
    fail("source Blender identity changed")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(source_blend))
source = bpy.data.objects.get(request["target_object"])
if source is None or source.type != "MESH":
    fail("registered gateway mesh is unavailable")

damage = source.copy()
damage.data = source.data.copy()
damage.name = "SM_AF_Module_Gateway_Damaged_Editable"
bpy.context.scene.collection.objects.link(damage)
local_bounds = [Vector(corner) for corner in damage.bound_box]
local_min = Vector(
    (
        min(corner.x for corner in local_bounds),
        min(corner.y for corner in local_bounds),
        min(corner.z for corner in local_bounds),
    )
)
local_max = Vector(
    (
        max(corner.x for corner in local_bounds),
        max(corner.y for corner in local_bounds),
        max(corner.z for corner in local_bounds),
    )
)
local_center = (local_min + local_max) * 0.5
damage.location = (-local_center.x, -local_center.y, -local_min.z)
damage["artflow_request_sha256"] = request["request_sha256"]
damage["artflow_source_object"] = source.name
source.hide_render = True
source.hide_viewport = True

field_image = bpy.data.images.load(str(field_path), check_existing=False)
field_image.name = "T_AF_GatewayDamage_Field"
field_image.colorspace_settings.name = "Non-Color"
field_image.pack()
pixels = list(field_image.pixels)
width, height = field_image.size
active = [
    (x, y, pixels[(y * width + x) * 4])
    for y in range(8, height - 8, 8)
    for x in range(8, width - 8, 8)
    if pixels[(y * width + x) * 4] >= 0.5
]
if len(active) < request["chip_count"]:
    fail("damage field returned too few usable chip sites")
step = max(1, len(active) // request["chip_count"])
sites = [active[index] for index in range(0, len(active), step)][
    : request["chip_count"]
]

stone = bpy.data.materials.new("M_AF_DamagedStone")
stone.use_nodes = True
nodes = stone.node_tree.nodes
links = stone.node_tree.links
bsdf = nodes.get("Principled BSDF")
texture = nodes.new("ShaderNodeTexImage")
texture.name = "ArtFlow_DamageField"
texture.image = field_image
ramp = nodes.new("ShaderNodeValToRGB")
ramp.name = "ArtFlow_DamagePalette"
ramp.color_ramp.elements[0].position = 0.23
ramp.color_ramp.elements[0].color = (0.055, 0.045, 0.038, 1.0)
ramp.color_ramp.elements[1].position = 0.67
ramp.color_ramp.elements[1].color = (0.31, 0.25, 0.18, 1.0)
bump = nodes.new("ShaderNodeBump")
bump.inputs["Strength"].default_value = 0.32
bump.inputs["Distance"].default_value = 0.08
links.new(texture.outputs["Color"], ramp.inputs["Fac"])
links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
links.new(texture.outputs["Color"], bump.inputs["Height"])
links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
bsdf.inputs["Roughness"].default_value = 0.78
damage.data.materials.clear()
damage.data.materials.append(stone)

cutters: list[bpy.types.Object] = []
chip_manifest = []
for index, (px, py, intensity) in enumerate(sites, start=1):
    u = px / max(1, width - 1)
    v = py / max(1, height - 1)
    side = -1.68 if u < 0.74 else 1.68
    location = (side, -0.38, 0.42 + min(v, 0.82) * 3.35)
    scale = (0.19 + intensity * 0.1, 0.42, 0.25 + intensity * 0.13)
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=1,
        radius=1.0,
        location=location,
        rotation=(index * 0.19, index * 0.31, index * 0.47),
    )
    cutter = bpy.context.object
    cutter.name = f"AF_DamageCutter_{index:02d}"
    cutter.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    cutter.display_type = "WIRE"
    cutter.hide_render = True
    cutter["artflow_field_pixel"] = [px, py]
    cutters.append(cutter)
    modifier = damage.modifiers.new(f"ArtFlow Chip {index:02d}", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    chip_manifest.append(
        {
            "chip_id": f"chip-{index:02d}",
            "field_pixel": [px, py],
            "location_m": [round(value, 5) for value in location],
            "scale_m": [round(value, 5) for value in scale],
        }
    )

export_obj = damage.copy()
export_obj.data = damage.data.copy()
export_obj.name = "SM_AF_Module_Gateway_Damaged"
bpy.context.scene.collection.objects.link(export_obj)
select_only(export_obj)
for modifier in list(export_obj.modifiers):
    bpy.context.view_layer.objects.active = export_obj
    bpy.ops.object.modifier_apply(modifier=modifier.name)
bevel = export_obj.modifiers.new("ArtFlow Damage Edge Bevel", "BEVEL")
bevel.width = 0.018
bevel.segments = 2
bpy.ops.object.modifier_apply(modifier=bevel.name)
bpy.ops.mesh.primitive_cube_add(
    location=(0, 0, 3.872),
    scale=(2.1, 0.4, 0.528),
)
lintel = bpy.context.object
lintel.name = "AF_DamagePreservedLintel"
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
lintel.data.materials.append(stone)
bpy.ops.object.select_all(action="DESELECT")
export_obj.select_set(True)
lintel.select_set(True)
bpy.context.view_layer.objects.active = export_obj
bpy.ops.object.join()
for material_index in reversed(range(len(export_obj.data.materials))):
    if export_obj.data.materials[material_index] is None:
        export_obj.data.materials.pop(index=material_index)
if len(export_obj.data.materials) == 0:
    export_obj.data.materials.append(stone)
for polygon in export_obj.data.polygons:
    polygon.material_index = 0
select_only(export_obj)
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.025)
bpy.ops.object.mode_set(mode="OBJECT")
export_obj.data.calc_loop_triangles()
triangle_count = len(export_obj.data.loop_triangles)
if triangle_count > request["triangle_budget"]:
    fail(
        f"damaged mesh exceeds triangle budget: {triangle_count}/"
        f"{request['triangle_budget']}"
    )
if export_obj.data.uv_layers.active is None:
    fail("damaged mesh has no UV set")

mask_copy = output_dir / "T_AF_GatewayDamage_Mask.png"
shutil.copyfile(field_path, mask_copy)
glb_path = output_dir / "SM_AF_Module_Gateway_Damaged.glb"
select_only(export_obj)
bpy.ops.export_scene.gltf(
    filepath=str(glb_path),
    export_format="GLB",
    use_selection=True,
    export_apply=True,
    export_materials="EXPORT",
)

manifest = {
    "schema_id": "artflow-damage-variant-manifest/1",
    "request_sha256": request["request_sha256"],
    "coordinate_system": "unreal-centimeters-z-up",
    "source_object": source.name,
    "editable_object": damage.name,
    "export_object": export_obj.name,
    "boolean_modifier_count": len(cutters),
    "chip_sites": chip_manifest,
    "triangle_count": triangle_count,
    "uv_layer": export_obj.data.uv_layers.active.name,
    "material_slots": [slot.material.name for slot in export_obj.material_slots],
    "glb": glb_path.name,
    "glb_sha256": sha256(glb_path),
    "damage_mask": mask_copy.name,
    "damage_mask_sha256": sha256(mask_copy),
}
manifest["manifest_sha256"] = canonical(manifest)
manifest_path = output_dir / "AF_GatewayDamage-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

for obj in bpy.context.scene.objects:
    if obj.type in {"MESH", "LIGHT", "CAMERA"}:
        obj.hide_render = obj != export_obj
export_obj.hide_render = False
bpy.ops.mesh.primitive_plane_add(size=16, location=(0, 0, -0.02))
ground = bpy.context.object
ground.name = "AF_DamagePreview_Ground"
ground.hide_render = False
ground_material = bpy.data.materials.new("M_AF_DamagePreviewGround")
ground_material.diffuse_color = (0.025, 0.035, 0.045, 1)
ground.data.materials.append(ground_material)
bpy.ops.object.camera_add(location=(8.2, -14.2, 7.0))
camera = bpy.context.object
camera.name = "ArtFlow_DamagePreview_Camera"
camera.rotation_euler = (
    Vector((0, 0, 2.0)) - camera.location
).to_track_quat("-Z", "Y").to_euler()
camera.data.lens = 52
bpy.context.scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(-4.5, -5.0, 8.0))
key = bpy.context.object
key.name = "ArtFlow_DamagePreview_Key"
key.data.energy = 1450
key.data.size = 5.0
key.rotation_euler = (
    Vector((0, 0, 2.0)) - key.location
).to_track_quat("-Z", "Y").to_euler()
bpy.ops.object.light_add(type="AREA", location=(4.5, -2.0, 4.5))
fill = bpy.context.object
fill.name = "ArtFlow_DamagePreview_Fill"
fill.data.energy = 900
fill.data.color = (0.32, 0.55, 1.0)
fill.data.size = 3.0
fill.rotation_euler = (
    Vector((0, 0, 2.1)) - fill.location
).to_track_quat("-Z", "Y").to_euler()
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.world.color = (0.006, 0.01, 0.018)
preview_path = output_dir / "AF_GatewayDamage-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)
blend_path = output_dir / "AF_GatewayDamage.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

payload = {
    "schema_id": "artflow-blender-damage-variant-receipt/1",
    "request_sha256": request["request_sha256"],
    "comfy_receipt_sha256": comfy["receipt_sha256"],
    "capability_id": request["blender_capability_id"],
    "status": "succeeded",
    "blender_version": bpy.app.version_string,
    "source_object": source.name,
    "editable_object": damage.name,
    "export_object": export_obj.name,
    "boolean_modifier_count": len(cutters),
    "triangle_count": triangle_count,
    "uv_layer": export_obj.data.uv_layers.active.name,
    "material_slots": [slot.material.name for slot in export_obj.material_slots],
    "artifacts": [
        artifact("blend", blend_path, output_dir),
        artifact("glb", glb_path, output_dir),
        artifact("material_mask", mask_copy, output_dir),
        artifact("preview", preview_path, output_dir),
        artifact("manifest", manifest_path, output_dir),
    ],
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "blender-damage-variant-receipt.json").write_text(
    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
)
print(
    f"ARTFLOW_DAMAGE_VARIANT_SUCCEEDED chips={len(cutters)} "
    f"triangles={triangle_count}"
)
