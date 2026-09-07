from __future__ import annotations

import hashlib
import json
import math
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


request_path, output_dir = (Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1:])
request = json.loads(request_path.read_text(encoding="utf-8"))
source_blend = Path(request["source_blend_path"])
if request.get("schema_id") != "artflow-simulation-cache-request/1" or sha256(source_blend) != request["source_blend_sha256"]:
    raise RuntimeError("ARTFLOW_SIMULATION_CACHE_FAILED: source identity mismatch")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(source_blend))
scene = bpy.context.scene
scene.frame_start, scene.frame_end, scene.render.fps = request["frame_start"], request["frame_end"], request["frame_rate"]
columns, rows = request["mesh_columns"], request["mesh_rows"]
verts = []
faces = []
for y in range(rows):
    v = y / (rows - 1)
    for x in range(columns):
        u = x / (columns - 1)
        verts.append(((u - 0.5) * 6.4, 1.8 + v * 0.3, 0.8 + v * 3.8))
for y in range(rows - 1):
    for x in range(columns - 1):
        a = y * columns + x
        faces.append((a, a + 1, a + 1 + columns, a + columns))
mesh = bpy.data.meshes.new("AF_WindVeil_Mesh")
mesh.from_pydata(verts, [], faces)
mesh.update()
veil = bpy.data.objects.new("AF_WindVeil", mesh)
bpy.context.collection.objects.link(veil)
wave = veil.modifiers.new("ArtFlow_BoundedWindWave", "WAVE")
wave.use_x, wave.use_y = True, False
wave.height = request["amplitude_m"]
wave.width = 1.25
wave.speed = 0.32
wave.narrowness = 2.1
wave.start_position_x = -3.2
solidify = veil.modifiers.new("ArtFlow_RenderThickness", "SOLIDIFY")
solidify.thickness = 0.025
veil["artflow_request_sha256"] = request["request_sha256"]
veil["artflow_frame_range"] = f"{request['frame_start']}-{request['frame_end']}"

material = bpy.data.materials.new("M_AF_WindVeil")
material.use_nodes = True
shader = material.node_tree.nodes.get("Principled BSDF")
shader.inputs["Base Color"].default_value = (0.025, 0.28, 0.32, 1.0)
shader.inputs["Metallic"].default_value = 0.38
shader.inputs["Roughness"].default_value = 0.28
shader.inputs["Emission Color"].default_value = (0.02, 0.7, 0.58, 1.0)
shader.inputs["Emission Strength"].default_value = 2.4
veil.data.materials.append(material)

bpy.ops.object.select_all(action="DESELECT")
veil.select_set(True)
bpy.context.view_layer.objects.active = veil
cache_path = output_dir / "AF_WindVeil_Cache.abc"
bpy.ops.wm.alembic_export(filepath=str(cache_path), start=request["frame_start"], end=request["frame_end"],
                          selected=True, flatten=True, uvs=True, normals=True, triangulate=True,
                          global_scale=1.0, as_background_job=False)
if not cache_path.is_file() or cache_path.stat().st_size <= 0:
    raise RuntimeError("ARTFLOW_SIMULATION_CACHE_FAILED: Alembic export missing")

camera = bpy.data.objects.get("AF_MaterialVariation_Camera") or bpy.data.objects.get("ArtFlow_Shot_Camera")
if camera is None:
    bpy.ops.object.camera_add(location=(9.5, -12.0, 7.5))
    camera = bpy.context.object
camera.location = (10.5, -12.5, 7.2)
camera.rotation_euler = (Vector((0, 0.4, 1.8)) - camera.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(-2, -4, 9))
bpy.context.object.data.energy = 1300
bpy.context.object.data.size = 7
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1280, 720, 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
previews = []
for kind, frame in (("preview_start", 1), ("preview_middle", 36), ("preview_end", 72)):
    scene.frame_set(frame)
    path = output_dir / f"AF_WindVeil_{frame:03d}.png"
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    previews.append((kind, path))
blend_path = output_dir / "AF_WindVeil_Cache.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

artifacts = [("blend", blend_path), ("alembic", cache_path), *previews]
payload = {"schema_id": "artflow-blender-simulation-cache-receipt/1", "request_sha256": request["request_sha256"],
           "capability_id": request["capability_id"], "status": "succeeded", "blender_version": bpy.app.version_string,
           "object_name": veil.name, "frame_range": [request["frame_start"], request["frame_end"]],
           "sample_count": 72, "vertex_count": len(verts), "face_count": len(faces),
           "max_displacement_m": request["amplitude_m"],
           "artifacts": [{"kind": kind, "relative_path": path.name, "sha256": sha256(path), "size_bytes": path.stat().st_size} for kind, path in artifacts],
           "elapsed_seconds": round(time.perf_counter() - started, 3),
           "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z")}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "blender-simulation-cache-receipt.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"ARTFLOW_SIMULATION_CACHE_SUCCEEDED cache_bytes={cache_path.stat().st_size}")
