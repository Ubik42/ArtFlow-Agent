from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import unreal


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow material variation failed: {message}")


repo = Path(__file__).resolve().parents[2]
evidence = repo / "artifacts/goal/m40-s1-material-variation"
m34 = repo / "artifacts/goal/m34-s1-pcg-density"
request_path = evidence / "material-variation-request.json"
blender_receipt_path = evidence / "blender-material-variation-receipt.json"
pcg_receipt_path = m34 / "unreal-native-pcg-density-receipt.json"
request = json.loads(request_path.read_text(encoding="utf-8"))
blender_receipt = json.loads(blender_receipt_path.read_text(encoding="utf-8"))
pcg_receipt = json.loads(pcg_receipt_path.read_text(encoding="utf-8"))
if blender_receipt.get("request_sha256") != request.get("request_sha256"):
    fail("Blender receipt does not belong to the material request")
if sha256(pcg_receipt_path) != request.get("native_pcg_receipt_sha256"):
    fail("native PCG candidate identity drifted")
if pcg_receipt.get("candidate_scene_path") != request.get("source_candidate_scene_path"):
    fail("material request points to another native PCG candidate")
for item in blender_receipt.get("variants", []):
    for path_key, hash_key in (
        ("base_color_texture", "base_color_sha256"),
        ("roughness_texture", "roughness_sha256"),
    ):
        if sha256(evidence / item[path_key]) != item[hash_key]:
            fail(f"Blender texture identity drifted: {item[path_key]}")

project = Path(unreal.Paths.project_dir()).resolve()
source_level = project / "Content/ArtFlowDemo.umap"
source_candidate_package = request["source_candidate_scene_path"]
source_candidate_file = (
    project / "Content" / (source_candidate_package.removeprefix("/Game/") + ".umap")
)
source_level_before = sha256(source_level)
source_candidate_before = sha256(source_candidate_file)
identity = request["request_sha256"][:12]
destination = f"/Game/ArtFlow/Generated/Materials/MV_{identity}"
asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
reconciled = True


def import_texture(source: Path, asset_name: str, *, srgb: bool) -> unreal.Texture2D:
    global reconciled
    object_path = f"{destination}/{asset_name}.{asset_name}"
    texture = (
        unreal.EditorAssetLibrary.load_asset(object_path)
        if unreal.EditorAssetLibrary.does_asset_exist(object_path)
        else None
    )
    source_hash = sha256(source)
    if texture is None:
        reconciled = False
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(source))
        task.set_editor_property("destination_path", destination)
        task.set_editor_property("destination_name", asset_name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", False)
        task.set_editor_property("save", True)
        asset_tools.import_asset_tasks([task])
        texture = unreal.EditorAssetLibrary.load_asset(object_path)
    if not isinstance(texture, unreal.Texture2D):
        fail(f"could not import {source.name}")
    existing_hash = unreal.EditorAssetLibrary.get_metadata_tag(texture, "ArtFlow.SourceSha256")
    if existing_hash and existing_hash != source_hash:
        fail(f"deterministic texture destination contains another source: {asset_name}")
    texture.set_editor_property("srgb", srgb)
    if not srgb:
        texture.set_editor_property(
            "compression_settings", unreal.TextureCompressionSettings.TC_MASKS
        )
    unreal.EditorAssetLibrary.set_metadata_tag(texture, "ArtFlow.SourceSha256", source_hash)
    unreal.EditorAssetLibrary.set_metadata_tag(
        texture, "ArtFlow.MaterialVariationRequestSha256", request["request_sha256"]
    )
    unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)
    return texture


textures: dict[str, dict[str, unreal.Texture2D]] = {}
texture_paths: dict[str, dict[str, str]] = {}
for index, item in enumerate(blender_receipt["variants"]):
    letter = "ABC"[index]
    base = import_texture(
        evidence / item["base_color_texture"],
        f"T_AF_Wayfinder_{letter}_BaseColor",
        srgb=True,
    )
    rough = import_texture(
        evidence / item["roughness_texture"],
        f"T_AF_Wayfinder_{letter}_Roughness",
        srgb=False,
    )
    textures[item["variant_id"]] = {"base_color": base, "roughness": rough}
    texture_paths[item["variant_id"]] = {
        "base_color": base.get_path_name(),
        "roughness": rough.get_path_name(),
    }

master_name = "M_AF_Wayfinder_SceneVariant_Master"
master_path = f"{destination}/{master_name}.{master_name}"
master = (
    unreal.EditorAssetLibrary.load_asset(master_path)
    if unreal.EditorAssetLibrary.does_asset_exist(master_path)
    else None
)
if master is None:
    reconciled = False
    master = asset_tools.create_asset(
        master_name, destination, unreal.Material, unreal.MaterialFactoryNew()
    )
    if not isinstance(master, unreal.Material):
        fail("could not create the registered material master")
    base_parameter = unreal.MaterialEditingLibrary.create_material_expression(
        master, unreal.MaterialExpressionTextureSampleParameter2D, -420, -100
    )
    base_parameter.set_editor_property("parameter_name", "BaseColor")
    base_parameter.set_editor_property("texture", textures["wayfinder-a"]["base_color"])
    rough_parameter = unreal.MaterialEditingLibrary.create_material_expression(
        master, unreal.MaterialExpressionTextureSampleParameter2D, -420, 110
    )
    rough_parameter.set_editor_property("parameter_name", "Roughness")
    rough_parameter.set_editor_property("texture", textures["wayfinder-a"]["roughness"])
    metallic_parameter = unreal.MaterialEditingLibrary.create_material_expression(
        master, unreal.MaterialExpressionScalarParameter, -420, 280
    )
    metallic_parameter.set_editor_property("parameter_name", "Metallic")
    metallic_parameter.set_editor_property("default_value", 0.35)
    if not unreal.MaterialEditingLibrary.connect_material_property(
        base_parameter, "RGB", unreal.MaterialProperty.MP_BASE_COLOR
    ):
        fail("could not connect BaseColor material parameter")
    if not unreal.MaterialEditingLibrary.connect_material_property(
        rough_parameter, "R", unreal.MaterialProperty.MP_ROUGHNESS
    ):
        fail("could not connect Roughness material parameter")
    if not unreal.MaterialEditingLibrary.connect_material_property(
        metallic_parameter, "", unreal.MaterialProperty.MP_METALLIC
    ):
        fail("could not connect Metallic material parameter")
    unreal.EditorAssetLibrary.set_metadata_tag(
        master, "ArtFlow.MaterialVariationRequestSha256", request["request_sha256"]
    )
    unreal.MaterialEditingLibrary.recompile_material(master)
    unreal.EditorAssetLibrary.save_loaded_asset(master, only_if_is_dirty=False)
elif not isinstance(master, unreal.Material):
    fail("registered material master has the wrong type")

instances: dict[str, unreal.MaterialInstanceConstant] = {}
instance_paths: dict[str, str] = {}
for item, palette in zip(blender_receipt["variants"], request["palettes"], strict=True):
    letter = item["variant_id"][-1].upper()
    name = f"MI_AF_Wayfinder_{letter}_SceneVariant"
    object_path = f"{destination}/{name}.{name}"
    instance = (
        unreal.EditorAssetLibrary.load_asset(object_path)
        if unreal.EditorAssetLibrary.does_asset_exist(object_path)
        else None
    )
    if instance is None:
        reconciled = False
        instance = asset_tools.create_asset(
            name,
            destination,
            unreal.MaterialInstanceConstant,
            unreal.MaterialInstanceConstantFactoryNew(),
        )
    if not isinstance(instance, unreal.MaterialInstanceConstant):
        fail(f"could not create material instance {name}")
    existing_request = unreal.EditorAssetLibrary.get_metadata_tag(
        instance, "ArtFlow.MaterialVariationRequestSha256"
    )
    if existing_request and existing_request != request["request_sha256"]:
        fail(f"material instance {name} belongs to another request")
    unreal.MaterialEditingLibrary.set_material_instance_parent(instance, master)
    unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
        instance, "BaseColor", textures[item["variant_id"]]["base_color"]
    )
    unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
        instance, "Roughness", textures[item["variant_id"]]["roughness"]
    )
    unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(
        instance, "Metallic", float(palette["metallic"])
    )
    unreal.EditorAssetLibrary.set_metadata_tag(
        instance, "ArtFlow.MaterialVariationRequestSha256", request["request_sha256"]
    )
    unreal.EditorAssetLibrary.set_metadata_tag(
        instance, "ArtFlow.BlenderReceiptSha256", blender_receipt["receipt_sha256"]
    )
    unreal.MaterialEditingLibrary.update_material_instance(instance)
    unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False)
    instances[item["variant_id"]] = instance
    instance_paths[item["variant_id"]] = instance.get_path_name()

candidate_name = f"Material_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    reconciled = False
    candidate = unreal.EditorAssetLibrary.duplicate_asset(
        source_candidate_package, candidate_package
    )
    if candidate is None:
        fail("could not derive material candidate from native PCG candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(candidate, only_if_is_dirty=False)
    del candidate
    unreal.SystemLibrary.collect_garbage()

world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load material candidate")
subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def variant_for_mesh(path: str) -> str | None:
    for letter in "ABC":
        if f"Wayfinder_{letter}" in path:
            return f"wayfinder-{letter.lower()}"
    return None


def apply_materials() -> tuple[int, dict[str, int], int]:
    component_count = 0
    instance_counts = {key: 0 for key in instances}
    changed = 0
    allowed_meshes = set(pcg_receipt["generated_mesh_paths"])
    for actor in subsystem.get_all_level_actors():
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = component.get_editor_property("static_mesh")
            if mesh is None or mesh.get_path_name() not in allowed_meshes:
                continue
            variant_id = variant_for_mesh(mesh.get_path_name())
            if variant_id is None:
                fail(f"could not resolve registered PCG mesh variant: {mesh.get_path_name()}")
            material = instances[variant_id]
            if component.get_material(0) != material:
                component.set_material(0, material)
                changed += 1
            component_count += 1
            instance_counts[variant_id] += component.get_instance_count()
    return component_count, instance_counts, changed


component_count, generated_counts, first_changed = apply_materials()
_, repeat_counts, repeat_changed = apply_materials()
if component_count != 3 or sum(generated_counts.values()) != 12:
    fail(
        f"expected three PCG components and twelve instances, got {component_count}/"
        f"{sum(generated_counts.values())}"
    )
if repeat_counts != generated_counts or repeat_changed != 0:
    fail("repeated material application was not idempotent")
unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

source_level_after = sha256(source_level)
source_candidate_after = sha256(source_candidate_file)
if source_level_before != source_level_after or source_candidate_before != source_candidate_after:
    fail("material application changed the source level or native PCG candidate")

actors = subsystem.get_all_level_actors()
camera = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_Camera"), None)
screenshot = evidence / "unreal-material-variation-candidate.png"
if screenshot.is_file():
    screenshot.unlink()
state = {"ticks": 0, "callback": None}


def finish() -> None:
    result = {
        "schema_id": "artflow-unreal-material-variation-receipt/1",
        "request_id": request["request_id"],
        "request_sha256": request["request_sha256"],
        "blender_receipt_sha256": blender_receipt["receipt_sha256"],
        "native_pcg_receipt_sha256": request["native_pcg_receipt_sha256"],
        "status": "reconciled" if reconciled and first_changed == 0 else "applied",
        "engine_version": unreal.SystemLibrary.get_engine_version(),
        "candidate_scene_path": candidate_package,
        "source_candidate_scene_path": source_candidate_package,
        "master_material_path": master.get_path_name(),
        "material_instance_paths": instance_paths,
        "imported_texture_paths": texture_paths,
        "assigned_component_count": component_count,
        "generated_instance_counts": generated_counts,
        "repeat_changed_component_count": repeat_changed,
        "duplicate_side_effect_count": 0,
        "source_level_sha256_before": source_level_before,
        "source_level_sha256_after": source_level_after,
        "source_candidate_sha256_before": source_candidate_before,
        "source_candidate_sha256_after": source_candidate_after,
        "screenshot_path": screenshot.name,
        "screenshot_sha256": sha256(screenshot) if screenshot.is_file() else None,
        "capture_status": "captured" if screenshot.is_file() else "unavailable",
        "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    result["receipt_sha256"] = canonical(result)
    (evidence / "unreal-material-variation-receipt.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    unreal.log(
        f"ARTFLOW_MATERIAL_VARIATION status={result['status']} "
        f"materials={len(instance_paths)} instances={sum(generated_counts.values())}"
    )
    if state["callback"] is not None:
        unreal.unregister_slate_post_tick_callback(state["callback"])
    unreal.SystemLibrary.quit_editor()


def on_tick(_delta_seconds: float) -> None:
    state["ticks"] += 1
    if screenshot.is_file() or state["ticks"] > 160:
        finish()


if isinstance(camera, unreal.CameraActor):
    unreal.AutomationLibrary.take_high_res_screenshot(
        1280, 720, str(screenshot), camera, False, False
    )
    state["callback"] = unreal.register_slate_post_tick_callback(on_tick)
    unreal.log("ARTFLOW_MATERIAL_VARIATION_PENDING waiting for same-camera capture")
else:
    finish()
