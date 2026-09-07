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
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def select_only(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]


def material(name, color, metallic, roughness):
    value = bpy.data.materials.new(name)
    value.diffuse_color = (*color, 1)
    value.metallic = metallic
    value.roughness = roughness
    value.use_nodes = True
    principled = value.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*color, 1)
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    return value


def cube(name, location, scale, assigned_material, bone_name):
    bpy.ops.mesh.primitive_cube_add(location=location, scale=scale)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(assigned_material)
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    bevel = obj.modifiers.new("Production Bevel", "BEVEL")
    bevel.width = 0.035
    bevel.segments = 2
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    return obj


request_path, output_dir = (Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1 :])
request = json.loads(request_path.read_text(encoding="utf-8"))
visual = Path(request["visual_target_path"])
if sha256(visual) != request["visual_target_sha256"]:
    raise RuntimeError("ARTFLOW_MECHANISM_FAILED: visual target identity mismatch")

started = time.perf_counter()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.fps = request["fps"]
scene.frame_start = request["frame_start"]
scene.frame_end = request["frame_end"]

frame_material = material("M_AF_GateFrame", (0.055, 0.075, 0.09), 0.82, 0.24)
panel_material = material("M_AF_GatePanel", (0.035, 0.31, 0.33), 0.66, 0.28)
accent_material = material("M_AF_GateAccent", (0.84, 0.42, 0.12), 0.5, 0.3)

width = request["width_cm"] / 100
height = request["height_cm"] / 100
depth = request["depth_cm"] / 100
post = 0.28
parts = [
    cube(
        "GateFrame_Left",
        (-width / 2 - post, 0, height / 2),
        (post, depth, height / 2),
        frame_material,
        "root",
    ),
    cube(
        "GateFrame_Right",
        (width / 2 + post, 0, height / 2),
        (post, depth, height / 2),
        frame_material,
        "root",
    ),
    cube(
        "GateFrame_Top",
        (0, 0, height + post),
        (width / 2 + post * 2, depth, post),
        frame_material,
        "root",
    ),
    cube("GateMotor", (0, 0, height + 0.62), (0.7, depth * 1.25, 0.32), accent_material, "root"),
]

leaf_width = width / 2 - 0.1
for side, center_x, hinge_name in (
    (-1, -width / 4, "hinge_left"),
    (1, width / 4, "hinge_right"),
):
    for slat_index in range(5):
        local = (slat_index - 2) * (leaf_width / 5)
        parts.append(
            cube(
                f"Gate_{hinge_name}_Slat_{slat_index + 1}",
                (center_x + local, 0, height * 0.48),
                (leaf_width / 12, depth * 0.58, height * 0.43),
                panel_material,
                hinge_name,
            )
        )
    for z in (height * 0.15, height * 0.5, height * 0.81):
        parts.append(
            cube(
                f"Gate_{hinge_name}_Rail_{round(z * 100)}",
                (center_x, 0, z),
                (leaf_width / 2, depth * 0.82, 0.075),
                accent_material if z == height * 0.5 else frame_material,
                hinge_name,
            )
        )

select_only(parts)
bpy.ops.object.join()
mesh = bpy.context.object
mesh.name = "SK_AF_ArticulatedGate"
if "UVMap" not in mesh.data.uv_layers:
    mesh.data.uv_layers.new(name="UVMap")
mesh.data.calc_loop_triangles()
triangle_count = len(mesh.data.loop_triangles)
if triangle_count > request["triangle_budget"]:
    raise RuntimeError("ARTFLOW_MECHANISM_FAILED: triangle budget exceeded")

armature_data = bpy.data.armatures.new("SKEL_AF_ArticulatedGate")
armature = bpy.data.objects.new("RIG_AF_ArticulatedGate", armature_data)
scene.collection.objects.link(armature)
select_only([armature])
bpy.ops.object.mode_set(mode="EDIT")
root = armature_data.edit_bones.new("root")
root.head = (0, 0, 0)
root.tail = (0, 0, 0.8)
left = armature_data.edit_bones.new("hinge_left")
left.head = (-width / 2, 0, 0.25)
left.tail = (-width / 2, 0, height)
left.parent = root
right = armature_data.edit_bones.new("hinge_right")
right.head = (width / 2, 0, 0.25)
right.tail = (width / 2, 0, height)
right.parent = root
bpy.ops.object.mode_set(mode="POSE")

mesh.parent = armature
modifier = mesh.modifiers.new("ArtFlow Armature", "ARMATURE")
modifier.object = armature

action = bpy.data.actions.new("ACT_AF_Gate_OpenClose")
armature.animation_data_create()
armature.animation_data.action = action
joint_by_id = {item["joint_id"]: item for item in request["joints"]}
for bone_name in ("hinge_left", "hinge_right"):
    pose_bone = armature.pose.bones[bone_name]
    pose_bone.rotation_mode = "XYZ"
    for frame, angle in (
        (request["frame_start"], joint_by_id[bone_name]["closed_angle_deg"]),
        (request["frame_open"], joint_by_id[bone_name]["open_angle_deg"]),
        (request["frame_end"], joint_by_id[bone_name]["closed_angle_deg"]),
    ):
        pose_bone.rotation_euler.y = math.radians(angle)
        pose_bone.keyframe_insert(data_path="rotation_euler", index=1, frame=frame, group=bone_name)
bpy.ops.object.mode_set(mode="OBJECT")

fbx = output_dir / "SK_AF_ArticulatedGate.fbx"
select_only([mesh, armature])
bpy.ops.export_scene.fbx(
    filepath=str(fbx),
    use_selection=True,
    object_types={"ARMATURE", "MESH"},
    apply_unit_scale=True,
    apply_scale_options="FBX_SCALE_ALL",
    axis_forward="-Z",
    axis_up="Y",
    add_leaf_bones=False,
    bake_anim=True,
    bake_anim_use_all_bones=True,
    bake_anim_use_nla_strips=False,
    bake_anim_use_all_actions=False,
    bake_anim_force_startend_keying=True,
    bake_anim_simplify_factor=0.0,
)

manifest = {
    "schema_id": "artflow-mechanism-rig-manifest/1",
    "request_sha256": request["request_sha256"],
    "coordinate_system": "unreal-centimeters-z-up",
    "mesh_name": mesh.name,
    "skeleton_name": armature_data.name,
    "bones": [
        {"bone_name": "root", "parent_bone": None},
        {"bone_name": "hinge_left", "parent_bone": "root"},
        {"bone_name": "hinge_right", "parent_bone": "root"},
    ],
    "action_name": action.name,
    "frame_start": request["frame_start"],
    "frame_open": request["frame_open"],
    "frame_end": request["frame_end"],
    "fps": request["fps"],
    "vertex_count": len(mesh.data.vertices),
    "triangle_count": triangle_count,
    "material_slots": [slot.material.name for slot in mesh.material_slots],
    "uv_layer": "UVMap",
    "fbx_path": fbx.name,
    "fbx_sha256": sha256(fbx),
}
manifest["manifest_sha256"] = canonical(manifest)
manifest_path = output_dir / "AF_ArticulatedGate-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

scene.frame_set(request["frame_open"])
bpy.ops.mesh.primitive_plane_add(size=18, location=(0, 0, -0.04))
ground = bpy.context.object
ground_material = material("M_AF_GateGround", (0.045, 0.055, 0.065), 0.05, 0.55)
ground.data.materials.append(ground_material)
bpy.ops.object.camera_add(location=(8.5, -10.5, 6.2))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 0, 2.0)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.lens = 58
scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(-4.5, -5, 9))
bpy.context.object.data.energy = 1900
bpy.context.object.data.size = 7
bpy.ops.object.light_add(type="AREA", location=(5, 2, 5))
bpy.context.object.data.energy = 1100
bpy.context.object.data.color = (0.18, 0.65, 1.0)
scene.world = bpy.data.worlds.new("ArtFlow Mechanism World")
scene.world.color = (0.009, 0.014, 0.022)
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = (
    1280,
    720,
    100,
)
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
preview = output_dir / "AF_ArticulatedGate-open-preview.png"
scene.render.filepath = str(preview)
bpy.ops.render.render(write_still=True)
blend = output_dir / "AF_ArticulatedGate.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend))

artifacts = []
for kind, path in (
    ("blend", blend),
    ("fbx", fbx),
    ("preview", preview),
    ("manifest", manifest_path),
):
    artifacts.append(
        {
            "kind": kind,
            "relative_path": path.name,
            "sha256": sha256(path),
            "size_bytes": path.stat().st_size,
        }
    )
payload = {
    "schema_id": "artflow-blender-mechanism-rig-receipt/1",
    "request_sha256": request["request_sha256"],
    "capability_id": request["blender_capability_id"],
    "status": "succeeded",
    "blender_version": bpy.app.version_string,
    "mesh_name": mesh.name,
    "skeleton_name": armature_data.name,
    "bone_count": len(armature_data.bones),
    "joint_count": 2,
    "action_name": action.name,
    "action_frame_range": [request["frame_start"], request["frame_end"]],
    "keyed_pose_count": 6,
    "vertex_count": len(mesh.data.vertices),
    "triangle_count": triangle_count,
    "material_slot_count": len(mesh.material_slots),
    "uv_layer": "UVMap",
    "artifacts": artifacts,
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "blender-mechanism-rig-receipt.json").write_text(
    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
)
print(
    f"ARTFLOW_MECHANISM_SUCCEEDED bones={payload['bone_count']} action={action.name} triangles={triangle_count}"
)
