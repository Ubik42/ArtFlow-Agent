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


def route_curve(name, points, radius_m, material):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for point, coordinate in zip(spline.bezier_points, points, strict=True):
        point.co = coordinate
        point.handle_left_type = "AUTO"
        point.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)

    group = bpy.data.node_groups.new(f"GN_{name}", "GeometryNodeTree")
    group.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    group.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    source = group.nodes.new("NodeGroupInput")
    target = group.nodes.new("NodeGroupOutput")
    resample = group.nodes.new("GeometryNodeResampleCurve")
    resample.inputs["Count"].default_value = 32
    profile = group.nodes.new("GeometryNodeCurvePrimitiveCircle")
    profile.inputs["Resolution"].default_value = 10
    profile.inputs["Radius"].default_value = radius_m
    to_mesh = group.nodes.new("GeometryNodeCurveToMesh")
    group.links.new(source.outputs["Geometry"], resample.inputs["Curve"])
    group.links.new(resample.outputs["Curve"], to_mesh.inputs["Curve"])
    group.links.new(profile.outputs["Curve"], to_mesh.inputs["Profile Curve"])
    group.links.new(to_mesh.outputs["Mesh"], target.inputs["Geometry"])
    modifier = obj.modifiers.new("ArtFlow Spline Infrastructure", "NODES")
    modifier.node_group = group
    return obj, group.name


request_path, output_dir = (Path(value).resolve() for value in sys.argv[sys.argv.index("--") + 1 :])
request = json.loads(request_path.read_text(encoding="utf-8"))
corridor = json.loads(
    (output_dir / "comfy-route-corridor-receipt.json").read_text(encoding="utf-8")
)
corridor_path = output_dir / corridor["corridor_path"]
if (
    corridor["request_sha256"] != request["request_sha256"]
    or sha256(corridor_path) != corridor["corridor_sha256"]
):
    raise RuntimeError("ARTFLOW_SPLINE_FAILED: corridor identity mismatch")

started = time.perf_counter()
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"

materials = {}
for name, color, metallic in (
    ("Cable", (0.025, 0.035, 0.045, 1), 0.15),
    ("Pipe", (0.14, 0.38, 0.41, 1), 0.72),
    ("Support", (0.17, 0.19, 0.21, 1), 0.8),
):
    material = bpy.data.materials.new(f"M_AF_{name}")
    material.diffuse_color = color
    material.metallic = metallic
    material.roughness = 0.32 if name != "Cable" else 0.48
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = color
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = material.roughness
    materials[name] = material

bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.09, depth=1.0, location=(0, 0, 0))
segment = bpy.context.object
segment.name = "SM_AF_SplineSegment"
segment.rotation_euler.y = math.radians(90)
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
segment.data.materials.append(materials["Pipe"])
segment_path = output_dir / "SM_AF_SplineSegment.glb"
select_only([segment])
bpy.ops.export_scene.gltf(
    filepath=str(segment_path),
    export_format="GLB",
    use_selection=True,
    export_apply=True,
    export_materials="EXPORT",
)

bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0.65), scale=(0.14, 0.3, 0.65))
support = bpy.context.object
support.name = "SM_AF_SplineSupport"
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
support.data.materials.append(materials["Support"])
support_path = output_dir / "SM_AF_SplineSupport.glb"
select_only([support])
bpy.ops.export_scene.gltf(
    filepath=str(support_path),
    export_format="GLB",
    use_selection=True,
    export_apply=True,
    export_materials="EXPORT",
)
segment.hide_render = True
support.hide_render = True

route_manifest = []
support_manifest = []
route_objects = []
for route_index, route in enumerate(request["routes"]):
    points_cm = []
    count = request["max_control_points_per_route"]
    center_y = (0.5 - request["route_row_px"] / 359.0) * 1200 + (route_index * 260 - 130)
    for index in range(count):
        alpha = index / (count - 1)
        x_px = route["start_x_px"] + (route["end_x_px"] - route["start_x_px"]) * alpha
        x_cm = (x_px / 639.0 - 0.5) * 1600
        y_cm = center_y + math.sin(alpha * math.pi * 2 + route_index) * 85
        z_cm = route["elevation_cm"] + math.sin(alpha * math.pi) * (
            55 if route["kind"] == "power_cable" else 18
        )
        points_cm.append([round(x_cm, 2), round(y_cm, 2), round(z_cm, 2)])
    curve, recipe = route_curve(
        f"CRV_AF_{route['route_id'].replace('-', '_')}",
        [Vector((x / 100, y / 100, z / 100)) for x, y, z in points_cm],
        route["diameter_cm"] / 200,
        materials["Cable" if route["kind"] == "power_cable" else "Pipe"],
    )
    curve["artflow_route_id"] = route["route_id"]
    route_objects.append(curve)
    route_manifest.append(
        {
            "route_id": route["route_id"],
            "kind": route["kind"],
            "diameter_cm": route["diameter_cm"],
            "control_points_cm": points_cm,
            "geometry_nodes_recipe": recipe,
        }
    )
    for point_index in range(0, len(points_cm), 2):
        location = points_cm[point_index]
        duplicate = support.copy()
        duplicate.data = support.data
        duplicate.name = f"PREVIEW_SUPPORT_{route_index + 1}_{point_index + 1}"
        duplicate.location = (location[0] / 100, location[1] / 100, 0)
        duplicate.hide_render = False
        scene.collection.objects.link(duplicate)
        support_manifest.append(
            {
                "support_id": f"support-{route_index + 1}-{point_index + 1}",
                "route_id": route["route_id"],
                "location_cm": [location[0], location[1], 0.0],
            }
        )

manifest = {
    "schema_id": "artflow-spline-infrastructure-manifest/1",
    "request_sha256": request["request_sha256"],
    "coordinate_system": "unreal-centimeters-z-up",
    "routes": route_manifest,
    "supports": support_manifest,
    "segment_asset": segment_path.name,
    "support_asset": support_path.name,
}
manifest["manifest_sha256"] = canonical(manifest)
manifest_path = output_dir / "AF_SplineInfrastructure-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

bpy.ops.mesh.primitive_plane_add(size=22, location=(0, 0, 0))
ground = bpy.context.object
ground_material = bpy.data.materials.new("M_AF_Ground")
ground_material.diffuse_color = (0.055, 0.065, 0.075, 1)
ground.data.materials.append(ground_material)
bpy.ops.object.camera_add(location=(13, -17, 10))
camera = bpy.context.object
camera.rotation_euler = (
    (Vector((0, 2.0, 1.6)) - camera.location).to_track_quat("-Z", "Y").to_euler()
)
camera.data.lens = 54
scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(-5, -6, 12))
bpy.context.object.data.energy = 1700
bpy.context.object.data.size = 9
bpy.ops.object.light_add(type="AREA", location=(7, 3, 7))
bpy.context.object.data.energy = 900
bpy.context.object.data.color = (0.28, 0.72, 1.0)
scene.world = bpy.data.worlds.new("ArtFlow Spline World")
scene.world.color = (0.012, 0.018, 0.026)
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = (
    1280,
    720,
    100,
)
scene.render.image_settings.file_format = "PNG"
scene.view_settings.look = "AgX - Medium High Contrast"
preview = output_dir / "AF_SplineInfrastructure-preview.png"
scene.render.filepath = str(preview)
bpy.ops.render.render(write_still=True)
blend = output_dir / "AF_SplineInfrastructure.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(blend))

artifacts = []
for kind, path in (
    ("blend", blend),
    ("preview", preview),
    ("manifest", manifest_path),
    ("segment_glb", segment_path),
    ("support_glb", support_path),
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
    "schema_id": "artflow-blender-spline-infrastructure-receipt/1",
    "request_sha256": request["request_sha256"],
    "corridor_receipt_sha256": corridor["receipt_sha256"],
    "capability_id": request["blender_capability_id"],
    "status": "succeeded",
    "blender_version": bpy.app.version_string,
    "route_count": len(route_manifest),
    "control_point_count": sum(len(item["control_points_cm"]) for item in route_manifest),
    "support_count": len(support_manifest),
    "geometry_nodes_recipes": [item["geometry_nodes_recipe"] for item in route_manifest],
    "artifacts": artifacts,
    "elapsed_seconds": round(time.perf_counter() - started, 3),
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
payload["receipt_sha256"] = canonical(payload)
(output_dir / "blender-spline-infrastructure-receipt.json").write_text(
    json.dumps(payload, indent=2) + "\n", encoding="utf-8"
)
print(
    f"ARTFLOW_SPLINE_SUCCEEDED routes={len(route_manifest)} controls={payload['control_point_count']} supports={len(support_manifest)}"
)
