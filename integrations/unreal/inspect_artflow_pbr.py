from __future__ import annotations

import json
import os
from pathlib import Path

import unreal


request = json.loads(Path(os.environ["ARTFLOW_PBR_REQUEST"]).read_text(encoding="utf-8"))
output = Path(os.environ["ARTFLOW_PBR_INSPECTION"])
world = unreal.EditorLoadingAndSavingUtils.load_map(request["destination_scene_path"])
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
target = next(actor for actor in actors if actor.get_actor_label() == request["target_actor_label"])
component = target.get_component_by_class(unreal.StaticMeshComponent)
instance = unreal.EditorAssetLibrary.load_asset(
    f"{request['destination_root']}/{request['material_instance_name']}.{request['material_instance_name']}"
)
master = instance.get_editor_property("parent")
parameters = {}
for name in ("BaseColor", "Normal", "Roughness", "Metallic", "AmbientOcclusion"):
    texture = unreal.MaterialEditingLibrary.get_material_instance_texture_parameter_value(instance, name)
    parameters[name] = texture.get_path_name() if texture else None
texture_facts = {}
for item in request["textures"]:
    expected = {
        "base_color": "T_RuinAltar_BaseColor",
        "normal": "T_RuinAltar_NormalDX",
        "roughness": "T_RuinAltar_Roughness",
        "metallic": "T_RuinAltar_Metallic",
        "ambient_occlusion": "T_RuinAltar_AO",
    }[item["channel"]]
    texture = unreal.EditorAssetLibrary.load_asset(
        f"{request['destination_root']}/{expected}.{expected}"
    )
    texture_facts[item["channel"]] = {
        "path": texture.get_path_name(),
        "srgb": texture.get_editor_property("srgb"),
        "compression": str(texture.get_editor_property("compression_settings")),
        "source_sha256": unreal.EditorAssetLibrary.get_metadata_tag(texture, "ArtFlow.SourceSha256"),
    }
material_connections = {}
for name, material_property in {
    "base_color": unreal.MaterialProperty.MP_BASE_COLOR,
    "normal": unreal.MaterialProperty.MP_NORMAL,
    "roughness": unreal.MaterialProperty.MP_ROUGHNESS,
    "metallic": unreal.MaterialProperty.MP_METALLIC,
    "ambient_occlusion": unreal.MaterialProperty.MP_AMBIENT_OCCLUSION,
}.items():
    node = unreal.MaterialEditingLibrary.get_material_property_input_node(master, material_property)
    material_connections[name] = {
        "node_class": node.get_class().get_name() if node else None,
        "output": str(
            unreal.MaterialEditingLibrary.get_material_property_input_node_output_name(
                master, material_property
            )
        ),
    }
facts = {
    "schema_id": "unreal-pbr-inspection/1",
    "target_actor": target.get_actor_label(),
    "component_material": component.get_material(0).get_path_name(),
    "instance_parent": master.get_path_name(),
    "master_expression_count": unreal.MaterialEditingLibrary.get_num_material_expressions(master),
    "master_connections": material_connections,
    "parameters": parameters,
    "textures": texture_facts,
}
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
unreal.log(f"ARTFLOW_PBR_INSPECTION material={facts['component_material']}")
