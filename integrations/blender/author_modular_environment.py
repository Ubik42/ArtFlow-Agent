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


def canonical(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def select_only(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def cube(name, location, scale, material):
    bpy.ops.mesh.primitive_cube_add(location=location, scale=scale)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj


def make_module(spec, material):
    kind = spec["module_id"]
    w, d, h = spec["width_cm"] / 100, spec["depth_cm"] / 100, spec["height_cm"] / 100
    if kind == "wall":
        parts = [cube("wall_body", (0, 0, h / 2), (w / 2, d / 2, h / 2), material),
                 cube("wall_cap", (0, 0, h + 0.12), (w * 0.54, d * 0.7, 0.12), material)]
    elif kind == "pillar":
        parts = [cube("pillar_base", (0, 0, 0.16), (w * 0.7, d * 0.7, 0.16), material),
                 cube("pillar_shaft", (0, 0, h / 2), (w / 2, d / 2, h / 2), material),
                 cube("pillar_cap", (0, 0, h + 0.14), (w * 0.68, d * 0.68, 0.14), material)]
    else:
        parts = [cube("gateway_left", (-w * 0.4, 0, h / 2), (w * 0.1, d / 2, h / 2), material),
                 cube("gateway_right", (w * 0.4, 0, h / 2), (w * 0.1, d / 2, h / 2), material),
                 cube("gateway_lintel", (0, 0, h * 0.88), (w / 2, d / 2, h * 0.12), material)]
    select_only(parts)
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = f"SM_AF_Module_{kind.title()}"
    if "UVMap" not in obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    group = bpy.data.node_groups.new(f"GN_AF_Module_{kind.title()}", "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    source, target = group.nodes.new("NodeGroupInput"), group.nodes.new("NodeGroupOutput")
    transform = group.nodes.new("GeometryNodeTransform")
    group.links.new(source.outputs["Geometry"], transform.inputs["Geometry"])
    group.links.new(transform.outputs["Geometry"], target.inputs["Geometry"])
    modifier = obj.modifiers.new("ArtFlow Modular Recipe", "NODES")
    modifier.node_group = group
    obj["artflow_module_id"] = kind
    return obj


request_path, output_dir = (Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1:])
request = json.loads(request_path.read_text(encoding="utf-8"))
zones = json.loads((output_dir / "comfy-module-zone-receipt.json").read_text(encoding="utf-8"))
zone_path = output_dir / zones["zone_map_path"]
if zones["request_sha256"] != request["request_sha256"] or sha256(zone_path) != zones["zone_map_sha256"]:
    raise RuntimeError("ARTFLOW_MODULAR_FAILED: spatial receipt identity mismatch")
started = time.perf_counter()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
material = bpy.data.materials.new("M_AF_ModularStone")
material.diffuse_color = (0.22, 0.24, 0.25, 1)
modules, variants = {}, []
for index, spec in enumerate(request["modules"]):
    obj = make_module(spec, material)
    obj.location.x = (index - 1) * 5.2
    modules[spec["module_id"]] = obj
    obj.data.calc_loop_triangles()
    path = output_dir / f"{obj.name}.glb"
    select_only([obj])
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True, export_apply=True, export_materials="EXPORT")
    variants.append({"module_id": spec["module_id"], "object_name": obj.name, "glb": path.name,
                     "sha256": sha256(path), "triangles": len(obj.data.loop_triangles), "uv_layer": "UVMap",
                     "geometry_nodes_recipe": obj.modifiers[0].node_group.name})
image = bpy.data.images.load(str(zone_path), check_existing=False)
pixels, width, height = list(image.pixels), image.size[0], image.size[1]
positions = []
for y in range(12, height - 12, max(18, height // 7)):
    for x in range(12, width - 12, max(24, width // 9)):
        if pixels[(y * width + x) * 4] >= 0.5:
            positions.append((x, y))
if len(positions) < request["placement_budget"]:
    raise RuntimeError("ARTFLOW_MODULAR_FAILED: spatial graph returned too few module zones")
rng = random.Random(request["seed"])
placements = []
catalog = ["wall", "pillar", "wall", "pillar", "gateway"]
for index, (x, y) in enumerate(positions[:request["placement_budget"]]):
    kind = catalog[index % len(catalog)]
    location = [round((x / (width - 1) - 0.5) * 1600, 2), round((0.5 - y / (height - 1)) * 1200, 2), 25.0]
    placements.append({"placement_id": f"module-placement-{index + 1:02d}", "module_id": kind,
                       "location_cm": location, "yaw_deg": float((index % 4) * 90), "seed": rng.randrange(2**31)})
    duplicate = modules[kind].copy()
    duplicate.data = modules[kind].data
    duplicate.name = f"PREVIEW_{index + 1:02d}_{kind}"
    duplicate.location = (location[0] / 100, location[1] / 100, 0.25)
    duplicate.rotation_euler.z = math.radians((index % 4) * 90)
    scene.collection.objects.link(duplicate)
for obj in modules.values():
    obj.hide_render = True
manifest = {"schema_id": "artflow-modular-environment-manifest/1", "request_sha256": request["request_sha256"],
            "coordinate_system": "unreal-centimeters-z-up", "variants": variants, "placements": placements}
manifest["manifest_sha256"] = canonical(manifest)
manifest_path = output_dir / "AF_ModularEnvironment-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
bpy.ops.mesh.primitive_plane_add(size=22, location=(0, 0, 0))
ground = bpy.context.object
ground.data.materials.append(material)
bpy.ops.object.camera_add(location=(13, -16, 11))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 1.5, 1.2)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.lens = 52
scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(-4, -5, 13))
bpy.context.object.data.energy = 1800
bpy.context.object.data.size = 8
bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
bpy.context.object.rotation_euler = (math.radians(30), math.radians(-18), math.radians(-30))
bpy.context.object.data.energy = 2.0
scene.world = bpy.data.worlds.new("ArtFlow Modular World")
scene.world.color = (0.022, 0.03, 0.04)
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
preview = output_dir / "AF_ModularEnvironment-preview.png"
scene.render.filepath = str(preview)
bpy.ops.render.render(write_still=True)
blend = output_dir / "AF_ModularEnvironment.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend))
artifacts = [{"kind": kind, "relative_path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size}
             for kind, path in (("blend", blend), ("preview", preview), ("manifest", manifest_path))]
for variant in variants:
    path = output_dir / variant["glb"]
    artifacts.append({"kind": "glb", "relative_path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size})
payload = {"schema_id": "artflow-blender-modular-environment-receipt/1", "request_sha256": request["request_sha256"],
           "zone_receipt_sha256": zones["receipt_sha256"], "capability_id": request["blender_capability_id"],
           "status": "succeeded", "blender_version": bpy.app.version_string, "variants": variants,
           "placement_count": len(placements), "total_triangles": sum(item["triangles"] for item in variants),
           "artifacts": artifacts, "elapsed_seconds": round(time.perf_counter() - started, 3),
           "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "blender-modular-environment-receipt.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"ARTFLOW_MODULAR_SUCCEEDED variants={len(variants)} placements={len(placements)}")
