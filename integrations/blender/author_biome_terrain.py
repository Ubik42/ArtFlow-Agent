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
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


request_path, output_dir = (Path(v).resolve() for v in sys.argv[sys.argv.index("--") + 1:])
request = json.loads(request_path.read_text(encoding="utf-8"))
field_receipt_path = output_dir / "comfy-terrain-fields-receipt.json"
fields = json.loads(field_receipt_path.read_text(encoding="utf-8"))
height_path, biome_path = output_dir / fields["height_map_path"], output_dir / fields["biome_mask_path"]
if request.get("schema_id") != "artflow-terrain-biome-request/1" or fields.get("request_sha256") != request.get("request_sha256"):
    raise RuntimeError("ARTFLOW_TERRAIN_FAILED: request chain mismatch")
if sha256(height_path) != fields["height_map_sha256"] or sha256(biome_path) != fields["biome_mask_sha256"]:
    raise RuntimeError("ARTFLOW_TERRAIN_FAILED: field identity drifted")

started = time.perf_counter()
bpy.ops.wm.read_factory_settings(use_empty=True)
height_image = bpy.data.images.load(str(height_path), check_existing=False)
biome_image = bpy.data.images.load(str(biome_path), check_existing=False)
height_pixels = list(height_image.pixels)
biome_pixels = list(biome_image.pixels)
height_width, height_height = height_image.size
biome_width, biome_height = biome_image.size


def gray(pixels: list[float], width: int, x: int, y: int) -> float:
    return pixels[(y * width + x) * 4]
gx, gy = request["grid_x"], request["grid_y"]
bounds = request["bounds"]
verts = []
uvs = []
for y in range(gy):
    v = y / (gy - 1)
    for x in range(gx):
        u = x / (gx - 1)
        px = min(height_width - 1, round(u * (height_width - 1)))
        py = min(height_height - 1, round(v * (height_height - 1)))
        height = gray(height_pixels, height_width, px, py)
        # The protected center remains a flat working pad; terrain rises around it.
        central = abs(u - 0.5) < 0.17 and abs(v - 0.5) < 0.2
        z = 0.0 if central else (height - 0.28) * bounds["height_cm"] / 100.0
        verts.append(((u - 0.5) * bounds["width_cm"] / 100.0,
                      (v - 0.5) * bounds["depth_cm"] / 100.0, z))
        uvs.append((u, v))
faces = []
for y in range(gy - 1):
    for x in range(gx - 1):
        a = y * gx + x
        faces.append((a, a + 1, a + 1 + gx, a + gx))
mesh = bpy.data.meshes.new("SM_AF_BiomeTerrain")
mesh.from_pydata(verts, [], faces)
mesh.update()
terrain = bpy.data.objects.new("SM_AF_BiomeTerrain", mesh)
bpy.context.collection.objects.link(terrain)
uv_layer = mesh.uv_layers.new(name="ArtFlow_TerrainUV")
for polygon in mesh.polygons:
    for loop_index in polygon.loop_indices:
        uv_layer.data[loop_index].uv = uvs[mesh.loops[loop_index].vertex_index]

# Keep a readable, editable Geometry Nodes recipe on the delivered source.
group = bpy.data.node_groups.new("GN_AF_BoundedTerrain", "GeometryNodeTree")
group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
input_node = group.nodes.new("NodeGroupInput")
output_node = group.nodes.new("NodeGroupOutput")
smooth = group.nodes.new("GeometryNodeSetShadeSmooth")
smooth.domain = "FACE"
group.links.new(input_node.outputs["Geometry"], smooth.inputs["Geometry"])
group.links.new(smooth.outputs["Geometry"], output_node.inputs["Geometry"])
modifier = terrain.modifiers.new("ArtFlow_BoundedTerrain", "NODES")
modifier.node_group = group
terrain["artflow_request_sha256"] = request["request_sha256"]
terrain["artflow_height_sha256"] = fields["height_map_sha256"]
terrain["artflow_biome_sha256"] = fields["biome_mask_sha256"]

material = bpy.data.materials.new("M_AF_BiomeTerrain_Preview")
material.diffuse_color = (0.12, 0.27, 0.16, 1.0)
terrain.data.materials.append(material)
bpy.ops.mesh.primitive_cube_add(location=(0, 0, -0.45), scale=(2.6, 2.2, 0.35))
collision = bpy.context.object
collision.name = "UBX_SM_AF_BiomeTerrain_00"
collision.display_type = "WIRE"
collision.hide_render = True

bpy.ops.object.camera_add(location=(12.5, -15.5, 11.0))
camera = bpy.context.object
camera.data.lens = 50
camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
bpy.context.scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(-5, -6, 13))
bpy.context.object.data.energy = 1600
bpy.context.object.data.size = 8
bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
bpy.context.object.rotation_euler = (math.radians(28), math.radians(-20), math.radians(-35))
bpy.context.object.data.energy = 2.0
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
scene.render.image_settings.file_format = "PNG"
scene.world = bpy.data.worlds.new("ArtFlow_BiomeWorld")
scene.world.color = (0.025, 0.04, 0.06)
scene.view_settings.look = "AgX - Medium High Contrast"
preview_path = output_dir / "AF_BiomeTerrain-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)
blend_path = output_dir / "AF_BiomeTerrain.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

# Export only the terrain; collision is kept in the editable Blender source and named metadata.
bpy.ops.object.select_all(action="DESELECT")
terrain.select_set(True)
bpy.context.view_layer.objects.active = terrain
glb_path = output_dir / "SM_AF_BiomeTerrain.glb"
bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True,
                          export_apply=True, export_materials="EXPORT")
biome_points = []
for y in range(6, biome_height - 6, max(8, biome_height // 8)):
    for x in range(6, biome_width - 6, max(8, biome_width // 10)):
        if gray(biome_pixels, biome_width, x, y) >= 0.5 and len(biome_points) < 18:
            biome_points.append({"location_cm": [round((x / (biome_width - 1) - 0.5) * bounds["width_cm"], 2),
                                                   round((0.5 - y / (biome_height - 1)) * bounds["depth_cm"], 2), 24.0],
                                 "seed": request["seed"] + len(biome_points)})
manifest_path = output_dir / "biome-pcg-points.json"
manifest_path.write_text(json.dumps({"schema_id": "artflow-biome-pcg-points/1",
                                     "request_sha256": request["request_sha256"],
                                     "points": biome_points}, indent=2) + "\n", encoding="utf-8")
payload = {"schema_id": "artflow-blender-terrain-receipt/1", "request_sha256": request["request_sha256"],
           "field_receipt_sha256": fields["receipt_sha256"], "capability_id": request["blender_capability_id"],
           "status": "succeeded", "blender_version": bpy.app.version_string,
           "vertex_count": len(verts), "face_count": len(faces), "geometry_node_count": len(group.nodes),
           "uv_layer": "ArtFlow_TerrainUV", "collision_proxy": collision.name,
           "protected_center_flat": True, "biome_point_count": len(biome_points),
           "artifacts": [{"kind": kind, "relative_path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size}
                         for kind, path in (("blend", blend_path), ("glb", glb_path), ("preview", preview_path), ("pcg_manifest", manifest_path))],
           "elapsed_seconds": round(time.perf_counter() - started, 3),
           "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "blender-terrain-receipt.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"ARTFLOW_TERRAIN_SUCCEEDED vertices={len(verts)} points={len(biome_points)}")
