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
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def ue_vector_to_blender(value: list[float]) -> Vector:
    return Vector((value[1] / 100.0, -value[0] / 100.0, value[2] / 100.0))


def ue_direction(rotation: list[float]) -> Vector:
    pitch = math.radians(rotation[0])
    yaw = math.radians(rotation[1])
    ue = Vector((math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch)))
    return Vector((ue.y, -ue.x, ue.z)).normalized()


def artifact(kind: str, path: Path, root: Path) -> dict[str, object]:
    return {
        "kind": kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


argv = sys.argv[sys.argv.index("--") + 1 :]
if len(argv) != 3:
    raise RuntimeError("ARTFLOW_CAMERA_MOVE_FAILED: expected request, output and source blend")
request_path, output_dir, source_blend = (Path(value).resolve() for value in argv)
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-camera-move-request/1":
    raise RuntimeError("ARTFLOW_CAMERA_MOVE_FAILED: unsupported request")
unsigned = dict(request)
unsigned.pop("request_sha256")
if canonical(unsigned) != request["request_sha256"]:
    raise RuntimeError("ARTFLOW_CAMERA_MOVE_FAILED: request fingerprint changed")
if sha256(source_blend) != request["source_blend_sha256"]:
    raise RuntimeError("ARTFLOW_CAMERA_MOVE_FAILED: source blend identity changed")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(source_blend))
camera = bpy.data.objects.get("ArtFlow_Shot_Camera")
if camera is None or camera.type != "CAMERA":
    raise RuntimeError("ARTFLOW_CAMERA_MOVE_FAILED: registered camera is missing")
camera.animation_data_clear()
subject_origin = Vector((0.0, -4.5, 0.0))
for pose in request["poses"]:
    camera.location = ue_vector_to_blender(pose["location_cm"]) - subject_origin
    camera.rotation_euler = ue_direction(pose["rotation_deg"]).to_track_quat("-Z", "Y").to_euler()
    camera.keyframe_insert(data_path="location", frame=pose["frame"])
    camera.keyframe_insert(data_path="rotation_euler", frame=pose["frame"])

scene = bpy.context.scene
scene.camera = camera
scene.frame_start = request["playback_start_frame"]
scene.frame_end = request["playback_end_frame"] - 1
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
blend_path = output_dir / f"{request['output_stem']}.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

artifacts = [artifact("blend", blend_path, output_dir)]
for pose in request["poses"]:
    scene.frame_set(pose["frame"])
    preview = output_dir / f"{request['output_stem']}-{pose['label']}.png"
    scene.render.filepath = str(preview)
    bpy.ops.render.render(write_still=True)
    artifacts.append(artifact(f"preview_{pose['label']}", preview, output_dir))

start = Vector(request["poses"][0]["location_cm"])
end = Vector(request["poses"][-1]["location_cm"])
payload = {
    "schema_id": "artflow-blender-camera-move-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "capability_id": request["capability_id"],
    "blender_version": bpy.app.version_string,
    "status": "succeeded",
    "camera_label": camera.name,
    "keyframe_count": len(request["poses"]),
    "frame_numbers": [pose["frame"] for pose in request["poses"]],
    "translation_distance_cm": round((end - start).length, 4),
    "artifacts": artifacts,
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "blender-camera-move-receipt.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"ARTFLOW_CAMERA_MOVE_SUCCEEDED request={request['request_id']} keys=3")
