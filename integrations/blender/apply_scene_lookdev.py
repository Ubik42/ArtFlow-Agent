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
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def kelvin_rgb(kelvin: float) -> tuple[float, float, float]:
    t = kelvin / 100.0
    r = 255.0 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = (
        99.4708025861 * math.log(t) - 161.1195681661
        if t <= 66
        else 288.1221695283 * ((t - 60) ** -0.0755148492)
    )
    b = (
        255.0
        if t >= 66
        else (0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.044792731)
    )
    return tuple(max(0.0, min(255.0, c)) / 255.0 for c in (r, g, b))


request_path, output_dir, source_blend = (
    Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1 :]
)
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-scene-lookdev-request/1":
    raise RuntimeError("ARTFLOW_LOOKDEV_FAILED: unsupported request")
if sha256(source_blend) != request["source_blend_sha256"]:
    raise RuntimeError("ARTFLOW_LOOKDEV_FAILED: source blend identity mismatch")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(source_blend))
for item in request["material_tints"]:
    material = bpy.data.materials.get(item["target"])
    if material is None or not material.use_nodes:
        raise RuntimeError(f"ARTFLOW_LOOKDEV_FAILED: missing registered material {item['target']}")
    bsdf = material.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError(f"ARTFLOW_LOOKDEV_FAILED: missing Principled BSDF on {item['target']}")
    socket = bsdf.inputs["Base Color"]
    source_links = list(socket.links)
    tint = material.node_tree.nodes.new("ShaderNodeMixRGB")
    tint.name = "ArtFlow_Lookdev_Tint"
    tint.blend_type = "MIX"
    tint.inputs[0].default_value = item["blend"]
    tint.inputs[2].default_value = (*item["color_srgb"], 1.0)
    if source_links:
        source = source_links[0].from_socket
        material.node_tree.links.remove(source_links[0])
        material.node_tree.links.new(source, tint.inputs[1])
    else:
        tint.inputs[1].default_value = socket.default_value
    material.node_tree.links.new(tint.outputs[0], socket)
    material["artflow_lookdev_request_sha256"] = request["request_sha256"]

lights = {obj.get("artflow_role"): obj for obj in bpy.context.scene.objects if obj.type == "LIGHT"}
for item in request["light_rig"]:
    light = lights.get(item["role"])
    if light is None:
        raise RuntimeError(f"ARTFLOW_LOOKDEV_FAILED: missing registered light {item['role']}")
    light.data.energy = item["intensity_lux"]
    light.data.color = kelvin_rgb(item["temperature_kelvin"])
    light.data.use_shadow = item["cast_shadows"]

scene = bpy.context.scene
camera = bpy.data.objects.get("ArtFlow_Shot_Camera")
if camera is None:
    raise RuntimeError("ARTFLOW_LOOKDEV_FAILED: registered shot camera missing")
scene.camera = camera
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = (
    1280,
    720,
    100,
)
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0.65
stem = request["output_stem"]
blend_path = output_dir / f"{stem}.blend"
preview_path = output_dir / f"{stem}-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
bpy.ops.render.render(write_still=True)

payload = {
    "schema_id": "artflow-blender-lookdev-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "capability_id": request["capability_id"],
    "status": "succeeded",
    "blender_version": bpy.app.version_string,
    "camera_label": camera.name,
    "material_targets": [item["target"] for item in request["material_tints"]],
    "light_roles": [item["role"] for item in request["light_rig"]],
    "artifacts": [
        {
            "kind": "blend",
            "relative_path": blend_path.name,
            "sha256": sha256(blend_path),
            "size_bytes": blend_path.stat().st_size,
        },
        {
            "kind": "preview",
            "relative_path": preview_path.name,
            "sha256": sha256(preview_path),
            "size_bytes": preview_path.stat().st_size,
        },
    ],
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "lookdev-receipt.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(f"ARTFLOW_BLENDER_LOOKDEV_SUCCEEDED request={request['request_id']}")
