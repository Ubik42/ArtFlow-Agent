from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import unreal

CHANNELS = ("base_color", "normal", "roughness", "metallic", "ambient_occlusion")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow PBR return failed closed: {message}")


def actor_state(actor: unreal.Actor) -> str:
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    materials = []
    if component:
        materials = [
            component.get_material(index).get_path_name() if component.get_material(index) else "none"
            for index in range(component.get_num_materials())
        ]
    value = {
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_path_name(),
        "location": [actor.get_actor_location().x, actor.get_actor_location().y, actor.get_actor_location().z],
        "rotation": [actor.get_actor_rotation().roll, actor.get_actor_rotation().pitch, actor.get_actor_rotation().yaw],
        "scale": [actor.get_actor_scale3d().x, actor.get_actor_scale3d().y, actor.get_actor_scale3d().z],
        "tags": sorted(str(item) for item in actor.tags),
        "materials": materials,
    }
    return canonical_sha256(value)


repo_root = Path(os.environ["ARTFLOW_REPO_ROOT"]).resolve()
request_path = Path(os.environ["ARTFLOW_PBR_REQUEST"]).resolve()
result_path = Path(os.environ["ARTFLOW_PBR_IMPORT_RESULT"]).resolve()
if not request_path.is_relative_to(repo_root) or not result_path.is_relative_to(repo_root):
    fail("request or result escaped the repository")
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "unreal-pbr-return-request/1":
    fail("unsupported request schema")
unsigned = dict(request)
unsigned.pop("request_sha256", None)
if canonical_sha256(unsigned) != request.get("request_sha256"):
    fail("request fingerprint mismatch")
if request.get("authority_scope") != "project_local_unreal_fixture":
    fail("authority scope is not project-local")
if not request.get("destination_scene_path", "").startswith("/Game/ArtFlow/Staging/"):
    fail("only an ArtFlow staging scene is writable")
if request.get("target_actor_label") != "Editable_Form":
    fail("only Editable_Form may receive this material")
destination_root = request.get("destination_root", "")
if not destination_root.startswith("/Game/ArtFlow/Generated/"):
    fail("destination escaped the generated namespace")
textures = request.get("textures", [])
if len(textures) != 5 or {item.get("channel") for item in textures} != set(CHANNELS):
    fail("request must contain exactly five PBR channels")

project_root = Path(unreal.Paths.project_dir()).resolve()
source_map = project_root / "Content" / "ArtFlowDemo.umap"
source_before = sha256_file(source_map)
if source_before != request.get("source_scene_sha256"):
    fail("source scene fingerprint changed before import")
world = unreal.EditorLoadingAndSavingUtils.load_map(request["destination_scene_path"])
if not world:
    fail("candidate scene could not be loaded")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
target = next((actor for actor in actors if actor.get_actor_label() == "Editable_Form"), None)
protected = next((actor for actor in actors if actor.get_actor_label() == "Protected_Blockout"), None)
if target is None or protected is None:
    fail("candidate target or protected actor is missing")
protected_before = actor_state(protected)

asset_tools = unreal.AssetToolsHelpers.get_asset_tools()
imported: dict[str, unreal.Texture2D] = {}
imported_paths: dict[str, str] = {}
reconciled = True
for item in textures:
    channel = item["channel"]
    source = (repo_root / item["path"]).resolve()
    if not source.is_relative_to(repo_root) or not source.is_file():
        fail(f"{channel} source escaped or is missing")
    if sha256_file(source) != item["sha256"]:
        fail(f"{channel} source hash mismatch")
    asset_prefix = request["material_instance_name"].removeprefix("MI_")
    asset_name = f"T_{asset_prefix}_" + {
        "base_color": "BaseColor",
        "normal": "NormalDX",
        "roughness": "Roughness",
        "metallic": "Metallic",
        "ambient_occlusion": "AO",
    }[channel]
    object_path = f"{destination_root}/{asset_name}.{asset_name}"
    texture = (
        unreal.EditorAssetLibrary.load_asset(object_path)
        if unreal.EditorAssetLibrary.does_asset_exist(object_path)
        else None
    )
    if texture:
        if unreal.EditorAssetLibrary.get_metadata_tag(texture, "ArtFlow.SourceSha256") != item["sha256"]:
            fail(f"unrelated asset occupies {object_path}")
    else:
        reconciled = False
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(source))
        task.set_editor_property("destination_path", destination_root)
        task.set_editor_property("destination_name", asset_name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", False)
        task.set_editor_property("save", True)
        asset_tools.import_asset_tasks([task])
        texture = unreal.EditorAssetLibrary.load_asset(object_path)
    if not isinstance(texture, unreal.Texture2D):
        fail(f"Unreal failed to import {channel} as Texture2D")
    texture.set_editor_property("srgb", channel == "base_color")
    if channel == "normal":
        texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
    elif channel not in {"base_color"}:
        texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
    unreal.EditorAssetLibrary.set_metadata_tag(texture, "ArtFlow.SourceSha256", item["sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(texture, "ArtFlow.RequestSha256", request["request_sha256"])
    unreal.EditorAssetLibrary.set_metadata_tag(texture, "ArtFlow.Channel", channel)
    unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)
    imported[channel] = texture
    imported_paths[channel] = object_path

master_name = "M_ArtFlowPBRMaster"
master_path = f"{destination_root}/{master_name}.{master_name}"
master = (
    unreal.EditorAssetLibrary.load_asset(master_path)
    if unreal.EditorAssetLibrary.does_asset_exist(master_path)
    else None
)
if master is None:
    reconciled = False
    master = asset_tools.create_asset(master_name, destination_root, unreal.Material, unreal.MaterialFactoryNew())
    if master is None:
        fail("could not create PBR master material")
    bindings = [
        ("BaseColor", "base_color", unreal.MaterialProperty.MP_BASE_COLOR, "RGB", -500, -260),
        ("Normal", "normal", unreal.MaterialProperty.MP_NORMAL, "RGB", -500, -80),
        ("Roughness", "roughness", unreal.MaterialProperty.MP_ROUGHNESS, "R", -500, 100),
        ("Metallic", "metallic", unreal.MaterialProperty.MP_METALLIC, "R", -500, 280),
        ("AmbientOcclusion", "ambient_occlusion", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION, "R", -500, 460),
    ]
    for parameter, channel, material_property, output_name, x, y in bindings:
        expression = unreal.MaterialEditingLibrary.create_material_expression(
            master, unreal.MaterialExpressionTextureSampleParameter2D, x, y
        )
        expression.set_editor_property("parameter_name", parameter)
        expression.set_editor_property("texture", imported[channel])
        if not unreal.MaterialEditingLibrary.connect_material_property(
            expression, output_name, material_property
        ):
            fail(f"could not connect {parameter} to master material")
unreal.MaterialEditingLibrary.recompile_material(master)
unreal.EditorAssetLibrary.save_loaded_asset(master, only_if_is_dirty=False)

instance_name = request["material_instance_name"]
instance_path = f"{destination_root}/{instance_name}.{instance_name}"
instance = (
    unreal.EditorAssetLibrary.load_asset(instance_path)
    if unreal.EditorAssetLibrary.does_asset_exist(instance_path)
    else None
)
if instance:
    if unreal.EditorAssetLibrary.get_metadata_tag(instance, "ArtFlow.RequestSha256") != request["request_sha256"]:
        fail("unrelated material instance occupies deterministic destination")
else:
    reconciled = False
    factory = unreal.MaterialInstanceConstantFactoryNew()
    instance = asset_tools.create_asset(instance_name, destination_root, unreal.MaterialInstanceConstant, factory)
if not isinstance(instance, unreal.MaterialInstanceConstant):
    fail("could not create material instance")
unreal.MaterialEditingLibrary.set_material_instance_parent(instance, master)
for parameter, channel in {
    "BaseColor": "base_color",
    "Normal": "normal",
    "Roughness": "roughness",
    "Metallic": "metallic",
    "AmbientOcclusion": "ambient_occlusion",
}.items():
    unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(
        instance, parameter, imported[channel]
    )
unreal.EditorAssetLibrary.set_metadata_tag(instance, "ArtFlow.RequestSha256", request["request_sha256"])
unreal.MaterialEditingLibrary.update_material_instance(instance)
unreal.EditorAssetLibrary.save_loaded_asset(instance, only_if_is_dirty=False)

component = target.get_component_by_class(unreal.StaticMeshComponent)
if component is None:
    fail("Editable_Form has no StaticMeshComponent")
component.set_material(0, instance)
target.tags = list(set(target.tags) | {"ArtFlow.PBR", request["request_id"]})
protected_after = actor_state(protected)
if protected_after != protected_before:
    fail("protected actor changed before save")
unreal.EditorLoadingAndSavingUtils.save_map(world, request["destination_scene_path"])
source_after = sha256_file(source_map)
if source_after != source_before:
    fail("source ArtFlowDemo changed during candidate material return")

result = {
    "schema_id": "unreal-pbr-import-result/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "status": "reconciled" if reconciled else "imported",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "destination_scene_path": request["destination_scene_path"],
    "target_actor_label": request["target_actor_label"],
    "imported_texture_paths": imported_paths,
    "master_material_path": master_path,
    "material_instance_path": instance_path,
    "source_scene_sha256_before": source_before,
    "source_scene_sha256_after": source_after,
    "protected_state_before": protected_before,
    "protected_state_after": protected_after,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result_path.parent.mkdir(parents=True, exist_ok=True)
temporary = result_path.with_suffix(result_path.suffix + ".tmp")
temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
temporary.replace(result_path)
unreal.log(f"ARTFLOW_PBR_IMPORT_RESULT status={result['status']} instance={instance_path}")
