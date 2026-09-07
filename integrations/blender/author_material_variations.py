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
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def select_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def unwrap_and_coverage(obj: bpy.types.Object) -> float:
    select_only(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
    bpy.ops.object.mode_set(mode="OBJECT")
    layer = obj.data.uv_layers.get("UVMap") or obj.data.uv_layers.active
    if layer is None or not layer.data:
        raise RuntimeError(f"ARTFLOW_MATERIAL_VARIATION_FAILED: {obj.name} has no UVMap")
    us = [loop.uv.x for loop in layer.data]
    vs = [loop.uv.y for loop in layer.data]
    return round(min(1.0, max(0.0, (max(us) - min(us)) * (max(vs) - min(vs)))), 6)


def make_bake_material(
    name: str,
    visual: bpy.types.Image,
    tint: list[float],
    roughness: float,
) -> tuple[bpy.types.Material, bpy.types.Node, bpy.types.Node, bpy.types.Node]:
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    source = nodes.new("ShaderNodeTexImage")
    source.name = "ComfyUI_Visual_Target"
    source.label = "ComfyUI Visual Target"
    source.image = visual
    tint_node = nodes.new("ShaderNodeMixRGB")
    tint_node.name = "Scene_Tint"
    tint_node.blend_type = "MULTIPLY"
    tint_node.inputs[0].default_value = 1.0
    tint_node.inputs[2].default_value = (*tint, 1.0)
    rough_node = nodes.new("ShaderNodeRGB")
    rough_node.name = "Registered_Roughness"
    rough_node.outputs[0].default_value = (roughness, roughness, roughness, 1.0)
    material.node_tree.links.new(source.outputs["Color"], tint_node.inputs[1])
    material.node_tree.links.new(tint_node.outputs["Color"], emission.inputs["Color"])
    material.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material, emission, tint_node, rough_node


def bake_channel(
    obj: bpy.types.Object,
    material: bpy.types.Material,
    emission: bpy.types.Node,
    source_node: bpy.types.Node,
    output_path: Path,
    size: int,
) -> bpy.types.Image:
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for link in list(emission.inputs["Color"].links):
        links.remove(link)
    links.new(source_node.outputs[0], emission.inputs["Color"])
    image = bpy.data.images.new(output_path.stem, width=size, height=size, alpha=False)
    image.filepath_raw = str(output_path)
    image.file_format = "PNG"
    target = nodes.new("ShaderNodeTexImage")
    target.name = f"BakeTarget_{output_path.stem}"
    target.image = image
    nodes.active = target
    target.select = True
    select_only(obj)
    bpy.ops.object.bake(type="EMIT", margin=8, use_clear=True)
    image.save()
    nodes.remove(target)
    return image


def build_editable_material(
    material: bpy.types.Material,
    visual: bpy.types.Image,
    base_image: bpy.types.Image,
    rough_image: bpy.types.Image,
    palette: dict[str, object],
) -> int:
    nodes = material.node_tree.nodes
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.name = "ArtFlow_Scene_Variant"
    base = nodes.new("ShaderNodeTexImage")
    base.name = "Baked_BaseColor"
    base.image = base_image
    rough = nodes.new("ShaderNodeTexImage")
    rough.name = "Baked_Roughness"
    rough.image = rough_image
    rough.image.colorspace_settings.name = "Non-Color"
    source = nodes.new("ShaderNodeTexImage")
    source.name = "ComfyUI_Visual_Target_Source"
    source.label = "Bound ComfyUI Visual Target"
    source.image = visual
    source.hide = True
    shader.inputs["Metallic"].default_value = float(palette["metallic"])
    shader.inputs["Emission Strength"].default_value = float(palette["emission_strength"])
    material.node_tree.links.new(base.outputs["Color"], shader.inputs["Base Color"])
    material.node_tree.links.new(base.outputs["Color"], shader.inputs["Emission Color"])
    material.node_tree.links.new(rough.outputs["Color"], shader.inputs["Roughness"])
    material.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return len(nodes)


request_path, output_dir = (Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1 :])
request = json.loads(request_path.read_text(encoding="utf-8"))
visual_path = Path(request["visual_target_path"])
kit_blend_path = Path(request["kit_blend_path"])
if request.get("schema_id") != "artflow-material-variation-request/1":
    raise RuntimeError("ARTFLOW_MATERIAL_VARIATION_FAILED: unsupported request")
if sha256(visual_path) != request["visual_target_sha256"]:
    raise RuntimeError("ARTFLOW_MATERIAL_VARIATION_FAILED: visual target identity mismatch")
if sha256(kit_blend_path) != request["kit_blend_sha256"]:
    raise RuntimeError("ARTFLOW_MATERIAL_VARIATION_FAILED: kit blend identity mismatch")

started = time.perf_counter()
bpy.ops.wm.open_mainfile(filepath=str(kit_blend_path))
scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = 8
visual = bpy.data.images.load(str(visual_path), check_existing=False)
results = []

for obj in scene.objects:
    if obj.type == "MESH":
        obj.hide_render = True

for index, palette in enumerate(request["palettes"]):
    obj = bpy.data.objects.get(palette["object_name"])
    if obj is None or obj.type != "MESH":
        raise RuntimeError(f"ARTFLOW_MATERIAL_VARIATION_FAILED: missing {palette['object_name']}")
    obj.hide_render = False
    obj.hide_viewport = False
    obj.location = ((index - 1) * 2.25, 0.0, 0.0)
    coverage = unwrap_and_coverage(obj)
    if coverage < 0.45:
        raise RuntimeError(
            f"ARTFLOW_MATERIAL_VARIATION_FAILED: insufficient UV coverage {coverage}"
        )
    material, emission, base_source, rough_source = make_bake_material(
        palette["material_name"],
        visual,
        palette["base_tint"],
        float(palette["roughness"]),
    )
    obj.data.materials.clear()
    obj.data.materials.append(material)
    base_path = output_dir / f"T_AF_Wayfinder_{'ABC'[index]}_BaseColor.png"
    rough_path = output_dir / f"T_AF_Wayfinder_{'ABC'[index]}_Roughness.png"
    base_image = bake_channel(
        obj, material, emission, base_source, base_path, request["texture_size"]
    )
    rough_image = bake_channel(
        obj, material, emission, rough_source, rough_path, request["texture_size"]
    )
    node_count = build_editable_material(material, visual, base_image, rough_image, palette)
    obj["artflow_material_variant"] = palette["variant_id"]
    obj["artflow_request_sha256"] = request["request_sha256"]
    results.append(
        {
            "variant_id": palette["variant_id"],
            "object_name": obj.name,
            "material_name": material.name,
            "uv_layer": "UVMap",
            "uv_coverage": coverage,
            "shader_node_count": node_count,
            "base_color_texture": base_path.name,
            "base_color_sha256": sha256(base_path),
            "roughness_texture": rough_path.name,
            "roughness_sha256": sha256(rough_path),
        }
    )

# A compact lookdev stage makes the three bounded directions legible in one frame.
scene.render.engine = "BLENDER_EEVEE"
bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, -0.01))
ground = bpy.context.object
ground.name = "AF_MaterialVariation_Ground"
ground_material = bpy.data.materials.new("M_AF_MaterialVariation_Ground")
ground_material.diffuse_color = (0.025, 0.035, 0.045, 1.0)
ground.data.materials.append(ground_material)
bpy.ops.object.camera_add(location=(7.8, -11.2, 6.1))
camera = bpy.context.object
camera.name = "AF_MaterialVariation_Camera"
camera.data.lens = 58
camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(-4, -4, 7))
bpy.context.object.data.energy = 1100
bpy.context.object.data.shape = "DISK"
bpy.context.object.data.size = 5.5
bpy.ops.object.light_add(type="AREA", location=(4, 1, 4))
bpy.context.object.data.energy = 750
bpy.context.object.data.color = (0.35, 0.65, 1.0)
bpy.context.object.data.size = 4.0
scene.world.color = (0.008, 0.012, 0.02)
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
preview_path = output_dir / "AF_Wayfinder_MaterialVariations-preview.png"
scene.render.filepath = str(preview_path)
bpy.ops.render.render(write_still=True)
blend_path = output_dir / "AF_Wayfinder_MaterialVariations.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))

artifacts = [
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
]
payload = {
    "schema_id": "artflow-blender-material-variation-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "capability_id": request["capability_id"],
    "status": "succeeded",
    "blender_version": bpy.app.version_string,
    "variants": results,
    "artifacts": artifacts,
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "blender-material-variation-receipt.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(
    f"ARTFLOW_MATERIAL_VARIATION_SUCCEEDED request={request['request_id']} "
    f"variants={len(results)} textures={len(results) * 2}"
)
