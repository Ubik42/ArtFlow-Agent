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


def artifact(kind: str, path: Path, root: Path) -> dict[str, object]:
    return {
        "kind": kind,
        "relative_path": path.relative_to(root).as_posix(),
        "sha256": sha256(path),
        "size_bytes": path.stat().st_size,
    }


argv = sys.argv[sys.argv.index("--") + 1 :]
if len(argv) != 2:
    raise RuntimeError("ARTFLOW_BLENDER_PBR_FAILED: expected request and output directory")
request_path = Path(argv[0]).resolve()
output_dir = Path(argv[1]).resolve()
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-blender-pbr-assembly-request/1":
    raise RuntimeError("ARTFLOW_BLENDER_PBR_FAILED: unsupported request")
started = time.perf_counter()
source_blend = Path(request["source_blend"]).resolve()
if sha256(source_blend) != request["source_blend_sha256"]:
    raise RuntimeError("ARTFLOW_BLENDER_PBR_FAILED: blend identity mismatch")
for texture in request["textures"]:
    path = Path(texture["path"]).resolve()
    if sha256(path) != texture["sha256"]:
        raise RuntimeError(f"ARTFLOW_BLENDER_PBR_FAILED: {texture['channel']} identity mismatch")

bpy.ops.wm.open_mainfile(filepath=str(source_blend))
materials = [bpy.data.materials.get("M_AF_Stone"), bpy.data.materials.get("M_AF_Weathering")]
by_channel = {item["channel"]: item for item in request["textures"]}
for material in materials:
    if material is None:
        raise RuntimeError("ARTFLOW_BLENDER_PBR_FAILED: target material missing")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    for node in list(nodes):
        if node != bsdf and node.type in {"TEX_IMAGE", "NORMAL_MAP"}:
            nodes.remove(node)
    base = nodes.new("ShaderNodeTexImage")
    base.name = "ArtFlow_Comfy_BaseColor"
    base.image = bpy.data.images.load(by_channel["base_color"]["path"], check_existing=True)
    links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    roughness = nodes.new("ShaderNodeTexImage")
    roughness.name = "ArtFlow_Comfy_Roughness"
    roughness.image = bpy.data.images.load(by_channel["roughness"]["path"], check_existing=True)
    roughness.image.colorspace_settings.name = "Non-Color"
    links.new(roughness.outputs["Color"], bsdf.inputs["Roughness"])
    normal_texture = nodes.new("ShaderNodeTexImage")
    normal_texture.name = "ArtFlow_Comfy_Normal"
    normal_texture.image = bpy.data.images.load(by_channel["normal"]["path"], check_existing=True)
    normal_texture.image.colorspace_settings.name = "Non-Color"
    normal = nodes.new("ShaderNodeNormalMap")
    normal.name = "ArtFlow_Comfy_NormalMap"
    normal.inputs["Strength"].default_value = 0.65
    links.new(normal_texture.outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
    material["artflow_pbr_receipt_sha256"] = request["pbr_receipt_sha256"]

stem = request["output_stem"]
blend_path = output_dir / f"{stem}.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH" and obj.get("artflow_generated")]
bpy.ops.object.select_all(action="DESELECT")
for obj in mesh_objects:
    obj.select_set(True)
bpy.context.view_layer.objects.active = mesh_objects[0]
bpy.ops.object.duplicate(linked=False)
export_objects = list(bpy.context.selected_objects)
bpy.context.view_layer.objects.active = export_objects[0]
bpy.ops.object.join()
export_mesh = bpy.context.object
export_mesh.name = stem
glb_path = output_dir / f"{stem}.glb"
bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", use_selection=True, export_apply=True)
bpy.data.objects.remove(export_mesh, do_unlink=True)

preview_path = output_dir / f"{stem}-preview.png"
bpy.context.scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)
payload = {
    "schema_id": "artflow-blender-pbr-assembly-receipt/1",
    "request_sha256": request["request_sha256"],
    "modeling_receipt_sha256": request["modeling_receipt_sha256"],
    "pbr_receipt_sha256": request["pbr_receipt_sha256"],
    "blender_version": bpy.app.version_string,
    "status": "succeeded",
    "material_targets": [material.name for material in materials],
    "texture_channels": sorted(by_channel),
    "artifacts": [artifact("blend", blend_path, output_dir), artifact("glb", glb_path, output_dir), artifact("preview", preview_path, output_dir)],
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
(output_dir / "pbr-assembly-receipt.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"ARTFLOW_BLENDER_PBR_SUCCEEDED request={request['request_sha256'][:16]} glb={glb_path}")
