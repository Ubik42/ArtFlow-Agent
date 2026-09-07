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


def add_leaf(name, length, width, height, yaw, material):
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, height * 0.48), scale=(width / 2, 0.018, length / 2))
    obj = bpy.context.object
    obj.name = name
    obj.rotation_euler = (math.radians(-14), math.radians(10), yaw)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    return obj


def add_stem(name, height, radius, material, vertices=8):
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius, radius2=radius * 0.42,
                                   depth=height, location=(0, 0, height / 2))
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(material)
    return obj


def join_recipe(name, parts, species_id):
    select_only(parts)
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = name
    if "UVMap" not in obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    group = bpy.data.node_groups.new(f"GN_{name}_WindReady", "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    source = group.nodes.new("NodeGroupInput")
    smooth = group.nodes.new("GeometryNodeSetShadeSmooth")
    target = group.nodes.new("NodeGroupOutput")
    group.links.new(source.outputs["Geometry"], smooth.inputs["Geometry"])
    group.links.new(smooth.outputs["Geometry"], target.inputs["Geometry"])
    modifier = obj.modifiers.new("ArtFlow Foliage Recipe", "NODES")
    modifier.node_group = group
    obj["artflow_species_id"] = species_id
    obj["artflow_wind_vertex_policy"] = "uv-height-gradient"
    return obj


def make_variant(spec, index, material):
    species = spec["species_id"]
    height = spec["max_height_cm"] / 100.0
    blade_count = spec["blade_count"]
    base_parts = [add_stem(f"{species}_stem", height * 0.72, 0.055 + index * 0.01, material, 10)]
    for blade in range(blade_count):
        angle = math.tau * blade / blade_count
        length = height * (0.54 if species == "fern" else 0.7)
        width = 0.13 if species == "reed" else (0.24 if species == "fern" else 0.32)
        leaf = add_leaf(f"{species}_leaf_{blade:02d}", length, width, height, angle, material)
        leaf.location.x = math.cos(angle) * (0.05 + 0.025 * index)
        leaf.location.y = math.sin(angle) * (0.05 + 0.025 * index)
        base_parts.append(leaf)
    base = join_recipe(f"SM_AF_Foliage_{species.title()}", base_parts, species)
    lod_parts = [add_stem(f"{species}_lod_stem", height * 0.7, 0.06, material, 6)]
    for blade in range(max(2, blade_count // 3)):
        angle = math.tau * blade / max(2, blade_count // 3)
        lod_parts.append(add_leaf(f"{species}_lod_leaf_{blade}", height * 0.58,
                                  0.15 + index * 0.04, height * 0.92, angle, material))
    lod = join_recipe(f"SM_AF_Foliage_{species.title()}_LOD1", lod_parts, species)
    lod.hide_viewport = True
    lod.hide_render = True
    bpy.ops.mesh.primitive_cube_add(location=(0, 0, height * 0.35), scale=(0.24, 0.24, height * 0.35))
    collision = bpy.context.object
    collision.name = f"UBX_{base.name}_00"
    collision.hide_render = True
    collision.display_type = "WIRE"
    return base, lod, collision


request_path, output_dir = (Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1:])
request = json.loads(request_path.read_text(encoding="utf-8"))
mask = Path(request["biome_mask_path"])
points_path = Path(request["biome_points_path"])
if request.get("schema_id") != "artflow-foliage-kit-request/1":
    raise RuntimeError("ARTFLOW_FOLIAGE_FAILED: unsupported request")
if sha256(mask) != request["biome_mask_sha256"] or sha256(points_path) != request["biome_points_sha256"]:
    raise RuntimeError("ARTFLOW_FOLIAGE_FAILED: biome identity drifted")
points = json.loads(points_path.read_text(encoding="utf-8"))["points"]
if len(points) != request["instance_budget"]:
    raise RuntimeError("ARTFLOW_FOLIAGE_FAILED: instance budget differs from biome field")

started = time.perf_counter()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
materials = []
colors = [(0.11, 0.34, 0.22, 1), (0.18, 0.48, 0.25, 1), (0.28, 0.42, 0.16, 1)]
for spec, color in zip(request["species"], colors, strict=True):
    mat = bpy.data.materials.new(f"M_AF_Foliage_{spec['species_id'].title()}")
    mat.diffuse_color = color
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = 0.72
    materials.append(mat)

variants = []
bases = []
for index, (spec, material) in enumerate(zip(request["species"], materials, strict=True)):
    base, lod, collision = make_variant(spec, index, material)
    base.location.x = (index - 1) * 2.4
    lod.location.x = base.location.x
    collision.location.x = base.location.x
    bases.append(base)
    base.data.calc_loop_triangles()
    lod.data.calc_loop_triangles()
    if len(base.data.loop_triangles) > request["triangle_budget_per_variant"]:
        raise RuntimeError("ARTFLOW_FOLIAGE_FAILED: triangle budget exceeded")
    if len(lod.data.loop_triangles) > len(base.data.loop_triangles) * 0.6:
        raise RuntimeError("ARTFLOW_FOLIAGE_FAILED: LOD ratio exceeded")
    exports = []
    for obj, suffix in ((base, ""), (lod, "_LOD1")):
        path = output_dir / f"SM_AF_Foliage_{spec['species_id'].title()}{suffix}.glb"
        previous_render = obj.hide_render
        previous_viewport = obj.hide_viewport
        obj.hide_render = False
        obj.hide_viewport = False
        select_only([obj])
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                                  export_apply=True, export_materials="EXPORT")
        obj.hide_render = previous_render
        obj.hide_viewport = previous_viewport
        exports.append(path)
    variants.append({
        "species_id": spec["species_id"], "object_name": base.name,
        "base_glb": exports[0].name, "base_sha256": sha256(exports[0]),
        "lod1_glb": exports[1].name, "lod1_sha256": sha256(exports[1]),
        "base_triangles": len(base.data.loop_triangles), "lod1_triangles": len(lod.data.loop_triangles),
        "uv_layer": "UVMap", "geometry_nodes_recipe": base.modifiers[0].node_group.name,
        "collision_proxy": collision.name, "wind_strength": spec["wind_strength"],
        "wind_speed": spec["wind_speed"],
    })

rng = random.Random(request["seed"])
placements = []
for index, point in enumerate(points):
    species = request["species"][index % 3]["species_id"]
    placements.append({"point_id": f"foliage-point-{index + 1:02d}", "species_id": species,
                       "location_cm": point["location_cm"], "seed": point["seed"],
                       "yaw_deg": round(rng.uniform(0, 360), 3), "scale": round(rng.uniform(0.78, 1.22), 4)})
manifest = {"schema_id": "artflow-foliage-kit-manifest/1", "request_sha256": request["request_sha256"],
            "coordinate_system": "unreal-centimeters-z-up", "variants": variants, "placements": placements}
manifest["manifest_sha256"] = canonical(manifest)
manifest_path = output_dir / "AF_BiomeFoliage-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

# Truthful presentation scene: the three editable source plants plus a terrain-scale placement preview.
for placement in placements:
    source = bases[[item["species_id"] for item in request["species"]].index(placement["species_id"])]
    duplicate = source.copy()
    duplicate.data = source.data
    duplicate.name = f"PREVIEW_{placement['point_id']}"
    duplicate.location = (placement["location_cm"][0] / 100, placement["location_cm"][1] / 100, 0)
    duplicate.rotation_euler.z = math.radians(placement["yaw_deg"])
    duplicate.scale = (placement["scale"],) * 3
    scene.collection.objects.link(duplicate)
for base in bases:
    base.hide_render = True
bpy.ops.mesh.primitive_plane_add(size=22, location=(0, 2.5, -0.02))
ground = bpy.context.object
ground_mat = bpy.data.materials.new("M_AF_BiomeGround")
ground_mat.diffuse_color = (0.035, 0.07, 0.055, 1)
ground.data.materials.append(ground_mat)
bpy.ops.object.camera_add(location=(11, -14, 10))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 3.5, 0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.lens = 52
scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(-5, -5, 12))
bpy.context.object.data.energy = 1700
bpy.context.object.data.size = 9
bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
bpy.context.object.rotation_euler = (math.radians(32), math.radians(-18), math.radians(-28))
bpy.context.object.data.energy = 2.2
scene.world = bpy.data.worlds.new("ArtFlow Foliage World")
scene.world.color = (0.018, 0.03, 0.025)
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
preview = output_dir / "AF_BiomeFoliage-preview.png"
scene.render.filepath = str(preview)
bpy.ops.render.render(write_still=True)
blend = output_dir / "AF_BiomeFoliage.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend))

artifacts = [{"kind": kind, "relative_path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size}
             for kind, path in (("blend", blend), ("preview", preview), ("manifest", manifest_path))]
for variant in variants:
    for key in ("base_glb", "lod1_glb"):
        path = output_dir / variant[key]
        artifacts.append({"kind": key, "relative_path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size})
payload = {"schema_id": "artflow-blender-foliage-kit-receipt/1", "request_id": request["request_id"],
           "request_sha256": request["request_sha256"], "capability_id": request["blender_capability_id"],
           "status": "succeeded", "blender_version": bpy.app.version_string, "variants": variants,
           "placement_count": len(placements), "artifacts": artifacts,
           "elapsed_seconds": round(time.perf_counter() - started, 3),
           "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "blender-foliage-kit-receipt.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"ARTFLOW_FOLIAGE_SUCCEEDED variants={len(variants)} placements={len(placements)}")
