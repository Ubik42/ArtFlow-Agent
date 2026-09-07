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
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def triangles(obj: bpy.types.Object) -> int:
    obj.data.calc_loop_triangles()
    return len(obj.data.loop_triangles)


def select_only(items: list[bpy.types.Object]) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for item in items:
        item.select_set(True)
    bpy.context.view_layer.objects.active = items[0]


def cube(name: str, location: tuple[float, float, float], scale: tuple[float, float, float]):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return obj


def cylinder(name: str, vertices: int, radius: float, depth: float, location: tuple[float, float, float]):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    return obj


def join_parts(name: str, parts: list[bpy.types.Object], stone, inlay):
    select_only(parts)
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(stone)
    obj.data.materials.append(inlay)
    for index, polygon in enumerate(obj.data.polygons):
        polygon.material_index = 1 if index % 7 == 0 or polygon.center.z > 1.15 else 0
    if "UVMap" not in obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    # The modifier is intentionally retained in the .blend as the editable recipe boundary.
    group = bpy.data.node_groups.new(f"GN_{name}_Recipe", "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    input_node = group.nodes.new("NodeGroupInput")
    output_node = group.nodes.new("NodeGroupOutput")
    transform = group.nodes.new("GeometryNodeTransform")
    group.links.new(input_node.outputs["Geometry"], transform.inputs["Geometry"])
    group.links.new(transform.outputs["Geometry"], output_node.inputs["Geometry"])
    modifier = obj.modifiers.new("ArtFlow Procedural Recipe", "NODES")
    modifier.node_group = group
    obj["artflow_procedural_recipe"] = group.name
    return obj


def make_variant(letter: str, index: int, stone, inlay):
    height = (1.45, 1.75, 1.58)[index]
    width = (0.52, 0.44, 0.62)[index]
    parts = [cube(f"{letter}_Plinth", (0, 0, 0.15), (0.48, 0.42, 0.15))]
    if index == 0:
        parts += [
            cube(f"{letter}_Stem", (0, 0, height / 2), (width / 2, 0.22, height / 2)),
            cylinder(f"{letter}_Halo", 24, 0.38, 0.18, (0, 0, height + 0.18)),
        ]
    elif index == 1:
        parts += [
            cylinder(f"{letter}_Stem", 16, width / 2, height, (0, 0, height / 2)),
            cube(f"{letter}_Cap", (0, 0, height + 0.12), (0.38, 0.30, 0.12)),
            cylinder(f"{letter}_Lens", 20, 0.25, 0.2, (0, -0.25, height * 0.72)),
        ]
    else:
        parts += [
            cube(f"{letter}_Stem", (0, 0, height / 2), (width / 2, 0.25, height / 2)),
            cube(f"{letter}_WingL", (-0.42, 0, height * 0.68), (0.22, 0.18, 0.10)),
            cube(f"{letter}_WingR", (0.42, 0, height * 0.68), (0.22, 0.18, 0.10)),
            cylinder(f"{letter}_Beacon", 20, 0.24, 0.25, (0, 0, height + 0.15)),
        ]
    base = join_parts(f"SM_AF_Wayfinder_{letter}", parts, stone, inlay)
    base["artflow_variant_id"] = f"wayfinder-{letter.lower()}"
    base["artflow_collision"] = "box"
    # Deliberately coarse LOD; exported separately for deterministic engine admission.
    lod_parts = [
        cube(f"{letter}_LOD_Plinth", (0, 0, 0.15), (0.48, 0.42, 0.15)),
        cube(f"{letter}_LOD_Stem", (0, 0, height / 2), (width / 2, 0.25, height / 2)),
        cube(f"{letter}_LOD_Cap", (0, 0, height + 0.12), (0.32, 0.28, 0.12)),
    ]
    lod = join_parts(f"SM_AF_Wayfinder_{letter}_LOD1", lod_parts, stone, inlay)
    lod.hide_viewport = True
    lod.hide_render = True
    return base, lod, [0.62, 0.52, round(height + 0.3, 3)]


request_path, output_dir = (Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1:])
request = json.loads(request_path.read_text(encoding="utf-8"))
visual_path = Path(request["visual_target_path"])
if request.get("schema_id") != "artflow-procedural-kit-request/1" or sha256(visual_path) != request["visual_target_sha256"]:
    raise RuntimeError("ARTFLOW_PROCEDURAL_KIT_FAILED: request or visual target identity mismatch")
started = time.perf_counter()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"

stone = bpy.data.materials.new("M_AF_Stone")
stone.diffuse_color = (0.13, 0.16, 0.18, 1)
stone.use_nodes = True
stone.node_tree.nodes.get("Principled BSDF").inputs["Roughness"].default_value = 0.72
inlay = bpy.data.materials.new("M_AF_GeneratedInlay")
inlay.use_nodes = True
nodes = inlay.node_tree.nodes
image = bpy.data.images.load(str(visual_path), check_existing=False)
texture = nodes.new("ShaderNodeTexImage")
texture.image = image
bsdf = nodes.get("Principled BSDF")
inlay.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Base Color"])
inlay.node_tree.links.new(texture.outputs["Color"], bsdf.inputs["Emission Color"])
bsdf.inputs["Emission Strength"].default_value = 0.22
bsdf.inputs["Metallic"].default_value = 0.55
bsdf.inputs["Roughness"].default_value = 0.35

variants = []
bases = []
for index, letter in enumerate("ABC"):
    base, lod, extent = make_variant(letter, index, stone, inlay)
    base.location.x = (index - 1) * 1.7
    lod.location.x = base.location.x
    bases.append(base)
    base_path = output_dir / f"{base.name}.glb"
    lod_path = output_dir / f"{lod.name}.glb"
    for obj, path in ((base, base_path), (lod, lod_path)):
        original = obj.hide_viewport
        obj.hide_viewport = False
        select_only([obj])
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_apply=True)
        obj.hide_viewport = original
    variants.append({
        "variant_id": f"wayfinder-{letter.lower()}", "object_name": base.name,
        "base_glb": base_path.name, "base_sha256": sha256(base_path),
        "lod1_glb": lod_path.name, "lod1_sha256": sha256(lod_path),
        "base_triangles": triangles(base), "lod1_triangles": triangles(lod),
        "uv_layers": ["UVMap"], "material_slots": ["M_AF_Stone", "M_AF_GeneratedInlay"],
        "collision_kind": "box", "collision_extent_m": extent,
    })

rng = random.Random(request["seed"])
placements = []
for index in range(request["placement_count"]):
    angle = math.tau * index / request["placement_count"] + rng.uniform(-0.08, 0.08)
    radius = rng.uniform(3.1, 4.25)
    placements.append({
        "point_id": f"kit-point-{index + 1:02d}",
        "variant_id": f"wayfinder-{'abc'[index % 3]}",
        "location_m": [round(math.cos(angle) * radius, 5), round(math.sin(angle) * radius, 5), 0.0],
        "yaw_deg": round(math.degrees(angle) + 90, 3), "scale": round(rng.uniform(0.9, 1.12), 4),
    })

manifest = {
    "schema_id": "artflow-procedural-kit-manifest/1", "request_sha256": request["request_sha256"],
    "consumer_capability_id": request["consumer_capability_id"], "coordinate_system": "blender-meters-z-up",
    "variants": variants, "placements": placements,
}
manifest["manifest_sha256"] = canonical(manifest)
manifest_path = output_dir / "AF_Wayfinder_Kit-manifest.json"
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# Presentation scene stays editable: three source recipes plus linked placement previews.
for point in placements:
    source = bases["abc".index(point["variant_id"][-1])]
    duplicate = source.copy()
    duplicate.data = source.data
    duplicate.name = f"PREVIEW_{point['point_id']}"
    duplicate.location = point["location_m"]
    duplicate.rotation_euler.z = math.radians(point["yaw_deg"])
    duplicate.scale = (point["scale"],) * 3
    scene.collection.objects.link(duplicate)
for base in bases:
    base.hide_render = True
bpy.ops.object.camera_add(location=(10.8, -11.5, 8.2), rotation=(math.radians(67), 0, math.radians(42)))
camera = bpy.context.object
camera.data.lens = 48
scene.camera = camera
# Aim camera at courtyard center.
direction = -camera.location
camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
bpy.ops.object.light_add(type="AREA", location=(1, -2, 9))
bpy.context.object.data.energy = 1500
bpy.context.object.data.shape = "DISK"
bpy.context.object.data.size = 7
bpy.ops.object.light_add(type="SUN", location=(0, 0, 6))
bpy.context.object.rotation_euler = (math.radians(25), math.radians(-20), math.radians(35))
bpy.context.object.data.energy = 2.0
scene.world = bpy.data.worlds.new("ArtFlow World")
scene.world.color = (0.025, 0.035, 0.05)
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
preview_path = output_dir / "AF_Wayfinder_Kit-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)
blend_path = output_dir / "AF_Wayfinder_Kit.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

artifacts = []
for kind, path in (("blend", blend_path), ("preview", preview_path), ("manifest", manifest_path)):
    artifacts.append({"kind": kind, "relative_path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size})
payload = {
    "schema_id": "artflow-procedural-kit-receipt/1", "request_id": request["request_id"],
    "request_sha256": request["request_sha256"], "capability_id": request["capability_id"],
    "status": "succeeded", "blender_version": bpy.app.version_string,
    "variants": variants, "placements": placements, "artifacts": artifacts,
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "procedural-kit-receipt.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"ARTFLOW_PROCEDURAL_KIT_SUCCEEDED request={request['request_id']} variants={len(variants)} placements={len(placements)}")
