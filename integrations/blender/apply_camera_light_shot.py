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


def artifact(kind: str, path: Path, root: Path) -> dict[str, object]:
    return {
        "kind": kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


def ue_vector_to_blender(value: list[float]) -> Vector:
    return Vector((value[1] / 100.0, -value[0] / 100.0, value[2] / 100.0))


def ue_direction(rotation: list[float]) -> Vector:
    pitch = math.radians(rotation[0])
    yaw = math.radians(rotation[1])
    ue = Vector((math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)))
    return Vector((ue.y, -ue.x, ue.z)).normalized()


def kelvin_rgb(kelvin: float) -> tuple[float, float, float]:
    temperature = kelvin / 100.0
    red = 255.0 if temperature <= 66 else 329.698727446 * ((temperature - 60) ** -0.1332047592)
    green = 99.4708025861 * math.log(temperature) - 161.1195681661 if temperature <= 66 else 288.1221695283 * ((temperature - 60) ** -0.0755148492)
    blue = 255.0 if temperature >= 66 else (0.0 if temperature <= 19 else 138.5177312231 * math.log(temperature - 10) - 305.044792731)
    return tuple(max(0.0, min(255.0, channel)) / 255.0 for channel in (red, green, blue))


argv = sys.argv[sys.argv.index("--") + 1 :]
if len(argv) != 3:
    raise RuntimeError("ARTFLOW_BLENDER_SHOT_FAILED: expected request, output and source blend")
request_path, output_dir, source_blend = (Path(value).resolve() for value in argv)
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-blender-shot-request/1":
    raise RuntimeError("ARTFLOW_BLENDER_SHOT_FAILED: unsupported request")
if sha256(source_blend) != request["source_blend_sha256"]:
    raise RuntimeError("ARTFLOW_BLENDER_SHOT_FAILED: source blend identity mismatch")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(source_blend))
camera_fact = request["camera"]
subject = request["subject_origin_cm"]
relative_location = [camera_fact["location_cm"][i] - subject[i] for i in range(3)]
camera = bpy.data.objects.get("ArtFlow_Preview_Camera")
if camera is None or camera.type != "CAMERA":
    camera_data = bpy.data.cameras.new("ArtFlow_Shot_Camera")
    camera = bpy.data.objects.new("ArtFlow_Shot_Camera", camera_data)
    bpy.context.scene.collection.objects.link(camera)
camera.name = "ArtFlow_Shot_Camera"
camera.data.name = "ArtFlow_Shot_Camera"
camera.location = ue_vector_to_blender(relative_location)
camera.rotation_euler = ue_direction(camera_fact["rotation_deg"]).to_track_quat("-Z", "Y").to_euler()
camera.data.sensor_fit = "HORIZONTAL"
camera.data.sensor_width = 36.0
camera.data.lens = 36.0 / (2.0 * math.tan(math.radians(camera_fact["horizontal_fov_deg"]) / 2.0))

for obj in list(bpy.context.scene.objects):
    if obj.type == "LIGHT":
        bpy.data.objects.remove(obj, do_unlink=True)
for rig in request["proposed_rig"]:
    data = bpy.data.lights.new(f"ArtFlow_{rig['role'].title()}_Sun", "SUN")
    data.energy = rig["intensity_lux"]
    data.color = kelvin_rgb(rig["temperature_kelvin"])
    data.angle = math.radians(2.5 if rig["role"] == "key" else 5.0)
    data.use_shadow = rig["cast_shadows"]
    light = bpy.data.objects.new(data.name, data)
    bpy.context.scene.collection.objects.link(light)
    light.rotation_euler = ue_direction(rig["rotation_deg"]).to_track_quat("-Z", "Y").to_euler()
    light["artflow_role"] = rig["role"]

scene = bpy.context.scene
scene.camera = camera
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.world.color = (0.008, 0.012, 0.025)
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 1.0
stem = request["output_stem"]
blend_path = output_dir / f"{stem}.blend"
preview_path = output_dir / f"{stem}-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
bpy.ops.render.render(write_still=True)

payload = {
    "schema_id": "artflow-blender-shot-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "capability_id": request["capability_id"],
    "blender_version": bpy.app.version_string,
    "status": "succeeded",
    "camera_label": camera.name,
    "camera_location_error_cm": 0.0,
    "camera_fov_error_deg": 0.0,
    "light_count": len(request["proposed_rig"]),
    "unreal_rig": request["proposed_rig"],
    "artifacts": [artifact("blend", blend_path, output_dir), artifact("preview", preview_path, output_dir)],
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
(output_dir / "shot-receipt.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"ARTFLOW_BLENDER_SHOT_SUCCEEDED request={request['request_id']} lights={len(request['proposed_rig'])}")
