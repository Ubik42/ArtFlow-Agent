"""Read the adopted candidate's actual scene facts without saving any UE asset."""
import hashlib
import json
import os
import re
from pathlib import Path

import unreal


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


root = Path(unreal.Paths.project_dir()).resolve()
request_path = Path(os.environ["ARTFLOW_SCENE_PUBLISH_REQUEST"]).resolve()
request = json.loads(request_path.read_text(encoding="utf-8"))
decision = request["decision"]
scene = decision["candidate_scene"]
if not re.fullmatch(r"/Game/ArtFlow/Sessions/AF_[a-f0-9]{12}/Candidates/[A-Za-z0-9_]+", scene):
    raise ValueError("Candidate is outside the registered Session namespace")
candidate = root / "Content" / (scene.removeprefix("/Game/") + ".umap")
source = root / "Content/ArtFlowDemo.umap"
before = file_hash(source)
if file_hash(candidate) != decision["candidate_level_sha256"] or before != decision["source_level_sha256"]:
    raise ValueError("Adopted scene bytes changed")
unreal.EditorLoadingAndSavingUtils.load_map(scene)
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
protected = next(a for a in actors if a.get_actor_label() == "Protected_Blockout")
editable = next(a for a in actors if a.get_actor_label() == "Editable_Form")
component = protected.get_component_by_class(unreal.StaticMeshComponent)
location, rotation, scale = protected.get_actor_location(), protected.get_actor_rotation(), protected.get_actor_scale3d()
protected_hash = digest({
    "label": protected.get_actor_label(), "class": protected.get_class().get_path_name(),
    "location": [location.x, location.y, location.z],
    "rotation": [rotation.roll, rotation.pitch, rotation.yaw], "scale": [scale.x, scale.y, scale.z],
    "tags": sorted(str(t) for t in protected.tags),
    "materials": [component.get_material(i).get_path_name() if component.get_material(i) else "none"
                  for i in range(component.get_num_materials())] if component else [],
})
material = editable.get_component_by_class(unreal.StaticMeshComponent).get_material(0).get_path_name()
instances = sum(c.get_instance_count() for a in actors
                for c in a.get_components_by_class(unreal.InstancedStaticMeshComponent)
                if "ArtFlow.Generated" in {str(t) for t in c.component_tags})
if file_hash(source) != before or file_hash(candidate) != decision["candidate_level_sha256"]:
    raise ValueError("Read-only inspection changed scene bytes")
result = {
    "schema_id": "artflow-routed-publish-facts/1", "candidate_scene": scene,
    "candidate_level_sha256": file_hash(candidate), "source_level_sha256": before,
    "protected_state_sha256": protected_hash, "material_path": material,
    "generated_instance_count": instances, "engine_version": unreal.SystemLibrary.get_engine_version(),
    "source_save_count": 0,
}
result["facts_sha256"] = digest(result)
output = root / "Saved/ArtFlowSceneBridge/RoutedCandidateFacts" / (result["candidate_level_sha256"] + ".json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
unreal.log(f"ARTFLOW_ROUTED_FACTS instances={instances} path={output}")
