from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import unreal


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def actor_state(actor: unreal.Actor) -> str:
    component = actor.get_component_by_class(unreal.StaticMeshComponent)
    materials = []
    if component:
        materials = [
            component.get_material(index).get_path_name() if component.get_material(index) else "none"
            for index in range(component.get_num_materials())
        ]
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    scale = actor.get_actor_scale3d()
    return canonical_sha256(
        {
            "label": actor.get_actor_label(),
            "class": actor.get_class().get_path_name(),
            "location": [location.x, location.y, location.z],
            "rotation": [rotation.roll, rotation.pitch, rotation.yaw],
            "scale": [scale.x, scale.y, scale.z],
            "tags": sorted(str(item) for item in actor.tags),
            "materials": materials,
        }
    )


repo_root = Path(os.environ["ARTFLOW_REPO_ROOT"]).resolve()
plan_path = Path(os.environ["ARTFLOW_M13_PLAN"]).resolve()
output_path = Path(os.environ["ARTFLOW_M13_INSPECTION"]).resolve()
if not plan_path.is_relative_to(repo_root) or not output_path.is_relative_to(repo_root):
    raise RuntimeError("M13 inspection paths escaped the repository")
plan = json.loads(plan_path.read_text(encoding="utf-8"))
execution_path = Path(os.environ.get("ARTFLOW_M13_EXECUTION", "")).resolve()
execution = json.loads(execution_path.read_text(encoding="utf-8")) if execution_path.is_file() else {}
world = unreal.EditorLoadingAndSavingUtils.load_map(plan["candidate_destination"])
if not world:
    raise RuntimeError("M13 candidate could not be loaded")

operations = {item["domain"]: item for item in plan["operations"]}
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
editable = next(actor for actor in actors if actor.get_actor_label() == "Editable_Form")
protected = next(actor for actor in actors if actor.get_actor_label() == "Protected_Blockout")
light_actor = next(actor for actor in actors if actor.get_actor_label() == "ArtFlow_KeyLight")
editable_mesh = editable.get_component_by_class(unreal.StaticMeshComponent)
light = light_actor.get_component_by_class(unreal.LightComponent)
material_path = editable_mesh.get_material(0).get_path_name()

generated_instances = 0
generated_meshes: list[str] = []
for actor in actors:
    for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
        if "ArtFlow.Generated" in {str(tag) for tag in component.component_tags}:
            generated_instances += component.get_instance_count()
            mesh = component.get_editor_property("static_mesh")
            if mesh:
                generated_meshes.append(mesh.get_path_name())

source_map = repo_root / "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlowDemo.umap"
candidate_package = plan["candidate_destination"].removeprefix("/Game/") + ".umap"
candidate_map = repo_root / "integrations/unreal/ArtFlowBridgeHost/Content" / candidate_package
facts = {
    "schema_id": "artflow-m13-technical-evaluation/1",
    "plan_id": plan["plan_id"],
    "plan_sha256": plan["plan_sha256"],
    "status": "verified",
    "checks": {
        "material_instance_matches": material_path == operations["material"]["material_instance_path"],
        "project_asset_set_matches": sorted(set(generated_meshes))
        == sorted(operations["asset"]["approved_asset_paths"]),
        "pcg_instance_count": generated_instances,
        "pcg_budget_ok": generated_instances <= operations["pcg"]["max_generated_instances"],
        "lighting_intensity": light.get_editor_property("intensity"),
        "lighting_temperature_kelvin": light.get_editor_property("temperature"),
        "protected_actor_present": protected is not None,
        "protected_state_sha256": actor_state(protected),
        "source_level_sha256": sha256_file(source_map),
        "candidate_level_sha256": sha256_file(candidate_map),
    },
    "material_instance_path": material_path,
    "generated_asset_paths": sorted(set(generated_meshes)),
    "candidate_beauty_sha256": execution.get("candidate_beauty_sha256", ""),
}
required = [
    facts["checks"]["material_instance_matches"],
    facts["checks"]["project_asset_set_matches"],
    facts["checks"]["pcg_budget_ok"],
    generated_instances == 12,
    abs(facts["checks"]["lighting_intensity"] - operations["lighting"]["intensity"]) < 0.01,
    abs(
        facts["checks"]["lighting_temperature_kelvin"]
        - operations["lighting"]["temperature_kelvin"]
    )
    < 0.01,
]
if not all(required):
    facts["status"] = "rejected"
output_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
unreal.log(f"ARTFLOW_M13_TECHNICAL_EVALUATION status={facts['status']}")
if facts["status"] != "verified":
    raise RuntimeError("M13 technical evaluation rejected the candidate")
