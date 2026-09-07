from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import unreal


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow lookdev return failed: {message}")


def find_actor(actors: list[unreal.Actor], label: str) -> unreal.Actor | None:
    return next((actor for actor in actors if actor.get_actor_label() == label), None)


repo_root = Path(__file__).resolve().parents[2]
evidence_root = repo_root / "artifacts/goal/m24-s2-scene-lookdev"
shot_root = repo_root / "artifacts/goal/m23-s5-camera-light"
layout_root = repo_root / "artifacts/goal/m23-s4-geometry-layout"
request_path = evidence_root / "lookdev-request.json"
receipt_path = evidence_root / "lookdev-receipt.json"
request = json.loads(request_path.read_text(encoding="utf-8"))
receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
shot_return = json.loads(
    (shot_root / "unreal-shot-return-receipt.json").read_text(encoding="utf-8")
)
layout_return = json.loads((layout_root / "unreal-return-receipt.json").read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-scene-lookdev-request/1":
    fail("unsupported lookdev request")
if receipt.get("request_sha256") != request.get("request_sha256"):
    fail("Blender lookdev receipt does not match the request")
if file_sha256(shot_root / "AF_ShrineCourtyard_Shot.blend") != request["source_blend_sha256"]:
    fail("source Blender shot identity drifted")

project_root = Path(unreal.Paths.project_dir()).resolve()
source_map = project_root / "Content/ArtFlowDemo.umap"
source_before = file_sha256(source_map)
if source_before != request["source_level_sha256"]:
    fail("source level changed after the lookdev request was compiled")

identity = request["request_sha256"][:12]
candidate_name = f"Lookdev_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    world_asset = unreal.EditorAssetLibrary.duplicate_asset(
        shot_return["candidate_scene_path"], candidate_package
    )
    if world_asset is None:
        fail("could not duplicate the registered shot candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(world_asset, only_if_is_dirty=False)
    del world_asset
    unreal.SystemLibrary.collect_garbage()

world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load the isolated lookdev candidate")
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsystem.get_all_level_actors()

camera = find_actor(actors, request["camera"]["label"])
if not isinstance(camera, unreal.CameraActor):
    fail("registered camera is missing")
camera.set_actor_location(unreal.Vector(*request["camera"]["location_cm"]), False, False)
camera_rotation = request["camera"]["rotation_deg"]
camera.set_actor_rotation(
    unreal.Rotator(pitch=camera_rotation[0], yaw=camera_rotation[1], roll=camera_rotation[2]),
    False,
)
camera_component = camera.get_editor_property("camera_component")
camera_component.set_editor_property("field_of_view", request["camera"]["horizontal_fov_deg"])
camera_component.set_editor_property("aspect_ratio", request["camera"]["aspect_ratio"])

rig_by_role = {item["role"]: item for item in request["light_rig"]}
light_bindings = (
    ("key", "ArtFlow_KeyLight"),
    ("fill", "DirectionalLight"),
    ("rim", "ArtFlow_DCC_RimLight"),
)
for role, label in light_bindings:
    actor = find_actor(actors, label)
    if not isinstance(actor, unreal.DirectionalLight):
        fail(f"registered light is missing: {label}")
    item = rig_by_role[role]
    rotation = item["rotation_deg"]
    actor.set_actor_rotation(
        unreal.Rotator(pitch=rotation[0], yaw=rotation[1], roll=rotation[2]), False
    )
    component = actor.get_editor_property("directional_light_component")
    component.set_editor_property("intensity", item["intensity_lux"])
    component.set_editor_property("use_temperature", True)
    component.set_editor_property("temperature", item["temperature_kelvin"])
    component.set_editor_property("cast_shadows", item["cast_shadows"])
    actor.tags = ["ArtFlow.Lookdev", request["request_id"], f"ArtFlow.LightRole.{role}"]

generated_actor = find_actor(actors, layout_return["actor_label"])
if not isinstance(generated_actor, unreal.StaticMeshActor):
    fail("registered Blender scene actor is missing")
material_root = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Lookdev/L_{identity}"
material_name = f"M_AF_Lookdev_{identity}"
material_object = f"{material_root}/{material_name}.{material_name}"
material = unreal.EditorAssetLibrary.load_asset(material_object)
material_reconciled = isinstance(material, unreal.Material)
if not material_reconciled:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        material_name, material_root, unreal.Material, unreal.MaterialFactoryNew()
    )
    if material is None:
        fail("could not create bounded lookdev material")
    stone = request["material_tints"][0]["color_srgb"]
    base = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant3Vector, -220, 0
    )
    base.set_editor_property("constant", unreal.LinearColor(stone[0], stone[1], stone[2], 1.0))
    roughness = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionConstant, -220, 160
    )
    roughness.set_editor_property("r", 0.72)
    if not unreal.MaterialEditingLibrary.connect_material_property(
        base, "", unreal.MaterialProperty.MP_BASE_COLOR
    ):
        fail("could not bind registered stone tint")
    if not unreal.MaterialEditingLibrary.connect_material_property(
        roughness, "", unreal.MaterialProperty.MP_ROUGHNESS
    ):
        fail("could not bind registered roughness")
    unreal.EditorAssetLibrary.set_metadata_tag(
        material, "ArtFlow.LookdevRequestSha256", request["request_sha256"]
    )
    unreal.EditorAssetLibrary.set_metadata_tag(
        material, "ArtFlow.AcceptedArtifactSha256", request["accepted_artifact_sha256"]
    )
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)

component = generated_actor.get_editor_property("static_mesh_component")
for slot in range(component.get_num_materials()):
    component.set_material(slot, material)
generated_actor.tags = ["ArtFlow.Lookdev", request["request_id"], "ArtFlow.AcceptedVisualTarget"]
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

screenshot_path = evidence_root / "unreal-lookdev-candidate.png"
if screenshot_path.is_file():
    screenshot_path.unlink()
unreal.AutomationLibrary.take_high_res_screenshot(
    1280, 720, str(screenshot_path), camera, False, False
)
source_after = file_sha256(source_map)
if source_after != source_before:
    fail("source level changed while returning the lookdev candidate")

result = {
    "schema_id": "artflow-unreal-lookdev-return-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "blender_lookdev_receipt_sha256": receipt["receipt_sha256"],
    "status": "reconciled" if candidate_reconciled and material_reconciled else "imported",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "source_candidate_scene_path": shot_return["candidate_scene_path"],
    "candidate_scene_path": candidate_package,
    "generated_actor_label": generated_actor.get_actor_label(),
    "material_path": material.get_path_name(),
    "material_slot_override_count": component.get_num_materials(),
    "applied_light_roles": [item[0] for item in light_bindings],
    "source_level_sha256_before": source_before,
    "source_level_sha256_after": source_after,
    "screenshot_path": screenshot_path.name,
    "screenshot_sha256": None,
    "capture_status": "requested",
    "duplicate_side_effect_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical_sha256(result)
(evidence_root / "unreal-lookdev-return-receipt.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
unreal.log(
    f"ARTFLOW_LOOKDEV_RETURN_SUBMITTED status={result['status']} candidate={candidate_package}"
)
