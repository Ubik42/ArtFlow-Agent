from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import unreal


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow lighting-domain patch failed closed: {message}")


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
request_path = Path(
    os.environ.get("ARTFLOW_LIGHTING_REQUEST", os.environ.get("ARTFLOW_M9_LIGHTING_REQUEST", ""))
).resolve()
result_path = Path(
    os.environ.get("ARTFLOW_LIGHTING_RESULT", os.environ.get("ARTFLOW_M9_LIGHTING_RESULT", ""))
).resolve()
if not request_path.is_relative_to(repo_root) or not result_path.is_relative_to(repo_root):
    fail("request or result escaped the repository")
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "lighting-domain-patch-request/1":
    fail("unsupported request schema")
unsigned = dict(request)
request_sha = unsigned.pop("request_sha256", None)
if canonical_sha256(unsigned) != request_sha:
    fail("request fingerprint mismatch")
candidate_scene_path = request["candidate_scene_path"]
if not (
    candidate_scene_path == "/Game/ArtFlow/Staging/AF_cb2176a7a45bbad1"
    or candidate_scene_path.startswith("/Game/ArtFlow/Sessions/")
):
    fail("candidate escaped the registered ArtFlow candidate namespaces")

project_root = Path(unreal.Paths.project_dir()).resolve()
source_path = project_root / "Content" / "ArtFlowDemo.umap"
source_before = file_sha256(source_path)
if source_before != request["source_scene_sha256"]:
    fail("source scene fingerprint is stale")
world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_scene_path)
if not world:
    fail("candidate scene could not be loaded")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()


def by_label(label: str) -> unreal.Actor:
    actor = next((item for item in actors if item.get_actor_label() == label), None)
    if actor is None:
        fail(f"required actor is missing: {label}")
    return actor


protected = by_label("Protected_Blockout")
editable = by_label("Editable_Form")
light_actor = by_label("ArtFlow_KeyLight")
protected_before = actor_state(protected)
if protected_before != request["protected_state_sha256"]:
    fail("protected actor does not match the request")

mesh_component = editable.get_component_by_class(unreal.StaticMeshComponent)
if mesh_component is None or mesh_component.get_material(0) is None:
    fail("editable material binding is missing")
material_before = mesh_component.get_material(0).get_path_name()
if material_before != request["expected_material_path"]:
    fail("successful material domain is not the fingerprint-locked binding")


def generated_count() -> int:
    return sum(
        component.get_instance_count()
        for actor in actors
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
    )


instances_before = generated_count()
if instances_before != request["expected_instance_count"]:
    fail("successful PCG domain instance count changed before lighting patch")
light = light_actor.get_component_by_class(unreal.LightComponent)
if light is None:
    fail("key light component is missing")
intensity_before = float(light.get_editor_property("intensity"))
temperature_before = float(light.get_editor_property("temperature"))
reconciled = (
    abs(intensity_before - request["intensity"]) < 1e-6
    and bool(light.get_editor_property("use_temperature"))
    and abs(temperature_before - request["temperature_kelvin"]) < 1e-6
)
if not reconciled:
    light.set_editor_property("intensity", request["intensity"])
    light.set_editor_property("use_temperature", True)
    light.set_editor_property("temperature", request["temperature_kelvin"])
    if not unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_scene_path):
        fail("candidate map could not be saved")

instances_after = generated_count()
material_after = mesh_component.get_material(0).get_path_name()
protected_after = actor_state(protected)
source_after = file_sha256(source_path)
if instances_after != instances_before:
    fail("lighting patch changed PCG instances")
if material_after != material_before:
    fail("lighting patch changed material binding")
if protected_after != protected_before:
    fail("lighting patch changed protected actor")
if source_after != source_before:
    fail("lighting patch changed source scene")

result = {
    "schema_id": "lighting-domain-patch-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request_sha,
    "status": "reconciled" if reconciled else "executed",
    "candidate_scene_path": candidate_scene_path,
    "intensity_before": intensity_before,
    "intensity_after": float(light.get_editor_property("intensity")),
    "temperature_before": temperature_before,
    "temperature_after": float(light.get_editor_property("temperature")),
    "generated_instance_count_before": instances_before,
    "generated_instance_count_after": instances_after,
    "material_path_before": material_before,
    "material_path_after": material_after,
    "source_scene_sha256_before": source_before,
    "source_scene_sha256_after": source_after,
    "protected_state_before": protected_before,
    "protected_state_after": protected_after,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical_sha256(result)
result_path.parent.mkdir(parents=True, exist_ok=True)
temporary = result_path.with_suffix(result_path.suffix + ".tmp")
temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
temporary.replace(result_path)
unreal.log(
    f"ARTFLOW_LIGHTING_PATCH purpose={request['purpose']} status={result['status']} "
    f"intensity={result['intensity_after']} pcg_instances={instances_after}"
)
