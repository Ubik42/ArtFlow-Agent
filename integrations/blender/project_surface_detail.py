from __future__ import annotations

import hashlib
import json
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


def fail(message: str) -> None:
    raise RuntimeError(f"ARTFLOW_SURFACE_DETAIL_FAILED: {message}")


def artifact(kind: str, path: Path, root: Path) -> dict[str, object]:
    return {
        "kind": kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


argv = sys.argv[sys.argv.index("--") + 1 :]
if len(argv) != 4:
    fail("expected request, Comfy receipt, output directory and source blend")
request_path, comfy_receipt_path, output_dir, source_blend = (
    Path(value).resolve() for value in argv
)
request = json.loads(request_path.read_text(encoding="utf-8"))
comfy_receipt = json.loads(comfy_receipt_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-surface-detail-request/1":
    fail("unsupported request")
if comfy_receipt.get("schema_id") != "artflow-comfy-surface-detail-receipt/1":
    fail("unsupported Comfy receipt")
if comfy_receipt.get("request_sha256") != request.get("request_sha256"):
    fail("Comfy receipt belongs to another request")
if sha256(source_blend) != request["source_blend_sha256"]:
    fail("source blend identity mismatch")
detail_artifact = next(
    (item for item in comfy_receipt["artifacts"] if item["kind"] == "projection_texture"),
    None,
)
if detail_artifact is None:
    fail("generated detail artifact is missing")
detail_path = (output_dir / detail_artifact["relative_path"]).resolve()
if output_dir not in detail_path.parents or sha256(detail_path) != detail_artifact["sha256"]:
    fail("generated detail identity mismatch")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(source_blend))
target = bpy.data.objects.get(request["target_object"])
surface = bpy.data.objects.get("AF_ShrineCourtyard_Baked")
camera = bpy.data.objects.get("ArtFlow_Shot_Camera")
if target is None or target.type != "MESH":
    fail("registered inlay target is missing")
if surface is None or surface.type != "MESH":
    fail("registered baked surface is missing")
if camera is None or camera.type != "CAMERA":
    fail("registered camera is missing")

detail_image = bpy.data.images.load(str(detail_path), check_existing=False)
detail_image.name = "AF_Inlay_GeneratedDetail"
detail_image.colorspace_settings.name = "sRGB"

camera_side = 1.0 if camera.location.y >= 0 else -1.0
front_y = target.location.y + camera_side * (
    target.dimensions.y * 0.5 + request["projection_offset_m"]
)
bpy.ops.mesh.primitive_cube_add(
    size=2.0,
    location=(target.location.x, front_y, target.location.z),
)
decal = bpy.context.object
decal.name = request["output_stem"]
decal.data.name = f"{request['output_stem']}_Mesh"
decal.scale = (
    target.dimensions.x * request["projection_scale"] * 0.5,
    max(request["projection_offset_m"], 0.002),
    target.dimensions.z * request["projection_scale"] * 0.5,
)
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
decal["artflow_generated"] = True
decal["artflow_surface_detail_request_sha256"] = request["request_sha256"]
decal["artflow_target_object"] = request["target_object"]

material = bpy.data.materials.new("M_AF_ProjectedInlay")
material.use_nodes = True
material["artflow_surface_detail_request_sha256"] = request["request_sha256"]
nodes = material.node_tree.nodes
links = material.node_tree.links
bsdf = nodes.get("Principled BSDF")
source_node = nodes.new("ShaderNodeTexImage")
source_node.name = "ArtFlow_GeneratedDetail"
source_node.image = detail_image
links.new(source_node.outputs["Color"], bsdf.inputs["Base Color"])
if "Emission Color" in bsdf.inputs:
    links.new(source_node.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 0.65
bsdf.inputs["Metallic"].default_value = 0.55
bsdf.inputs["Roughness"].default_value = 0.34
decal.data.materials.append(material)

resolution = request["resolution"]
baked_image = bpy.data.images.new(
    "AF_Inlay_ProjectedDetail_Baked",
    width=resolution,
    height=resolution,
    alpha=False,
)
bake_node = nodes.new("ShaderNodeTexImage")
bake_node.name = "ArtFlow_ProjectionBakeTarget"
bake_node.image = baked_image
for node in nodes:
    node.select = False
bake_node.select = True
nodes.active = bake_node

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 1
scene.render.bake.margin = 8
bpy.context.view_layer.objects.active = decal
decal.select_set(True)
bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"})
baked_path = output_dir / f"{request['output_stem']}_BaseColor.png"
baked_image.filepath_raw = str(baked_path)
baked_image.file_format = "PNG"
baked_image.save()
links.remove(next(link for link in links if link.to_node == bsdf and link.to_socket == bsdf.inputs["Base Color"]))
links.new(bake_node.outputs["Color"], bsdf.inputs["Base Color"])
baked_image.pack()

bpy.ops.object.select_all(action="DESELECT")
decal.select_set(True)
bpy.context.view_layer.objects.active = decal
glb_path = output_dir / f"{request['output_stem']}.glb"
bpy.ops.export_scene.gltf(
    filepath=str(glb_path),
    export_format="GLB",
    use_selection=True,
    export_apply=True,
)

for obj in bpy.context.scene.objects:
    if obj.type == "MESH":
        obj.hide_render = obj not in {surface, decal}
surface.hide_render = False
decal.hide_render = False
scene.camera = camera
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0.65
preview_path = output_dir / f"{request['output_stem']}-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)
blend_path = output_dir / f"{request['output_stem']}.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

decal.data.calc_loop_triangles()
uv_layer = decal.data.uv_layers.active
if uv_layer is None:
    fail("projected detail has no UV set")
facts = {
    "schema_id": "artflow-blender-surface-detail-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "comfy_receipt_sha256": comfy_receipt["receipt_sha256"],
    "capability_id": request["blender_capability_id"],
    "status": "succeeded",
    "blender_version": bpy.app.version_string,
    "target_object": request["target_object"],
    "decal_object": decal.name,
    "vertex_count": len(decal.data.vertices),
    "triangle_count": len(decal.data.loop_triangles),
    "uv_loop_count": len(uv_layer.data),
    "material_slots": [slot.material.name for slot in decal.material_slots],
    "artifacts": [
        artifact("blend", blend_path, output_dir),
        artifact("glb", glb_path, output_dir),
        artifact("preview", preview_path, output_dir),
        artifact("baked_texture", baked_path, output_dir),
    ],
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
facts["receipt_sha256"] = canonical(facts)
(output_dir / "blender-surface-detail-receipt.json").write_text(
    json.dumps(facts, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print(
    f"ARTFLOW_SURFACE_DETAIL_SUCCEEDED request={request['request_id']} "
    f"vertices={len(decal.data.vertices)} triangles={len(decal.data.loop_triangles)}"
)
