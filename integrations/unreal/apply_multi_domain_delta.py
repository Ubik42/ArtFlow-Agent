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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow multi-domain execution failed closed: {message}")


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
    value = {
        "label": actor.get_actor_label(),
        "class": actor.get_class().get_path_name(),
        "location": [location.x, location.y, location.z],
        "rotation": [rotation.roll, rotation.pitch, rotation.yaw],
        "scale": [scale.x, scale.y, scale.z],
        "tags": sorted(str(item) for item in actor.tags),
        "materials": materials,
    }
    return canonical_sha256(value)


repo_root = Path(os.environ["ARTFLOW_REPO_ROOT"]).resolve()
request_path = Path(os.environ["ARTFLOW_M9_REQUEST"]).resolve()
result_path = Path(os.environ["ARTFLOW_M9_APPLY_RESULT"]).resolve()
if not request_path.is_relative_to(repo_root) or not result_path.is_relative_to(repo_root):
    fail("request or result escaped the repository")
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "multi-domain-unreal-request/1":
    fail("unsupported request schema")
unsigned = dict(request)
request_sha256 = unsigned.pop("request_sha256", None)
if canonical_sha256(unsigned) != request_sha256:
    fail("request fingerprint mismatch")
if request.get("operation_order") != [
    "asset-reuse", "lighting-patch", "material-bind", "pcg-layout"
]:
    fail("operation order is not the reviewed M9-S1 order")
if request.get("candidate_scene_path") != "/Game/ArtFlow/Staging/AF_cb2176a7a45bbad1":
    fail("only the content-addressed ArtFlow candidate is writable")

project_root = Path(unreal.Paths.project_dir()).resolve()
source_map = project_root / "Content" / "ArtFlowDemo.umap"
source_before = sha256_file(source_map)
if source_before != request.get("source_scene_sha256"):
    fail("source scene fingerprint is stale")
world = unreal.EditorLoadingAndSavingUtils.load_map(request["candidate_scene_path"])
if not world:
    fail("candidate scene could not be loaded")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
bindings = {item["role"]: item for item in request["actors"]}
resolved = {}
for role, binding in bindings.items():
    actor = next((item for item in actors if item.get_actor_label() == binding["label"]), None)
    if actor is None:
        fail(f"bound actor is missing: {role}")
    resolved[role] = actor
target = resolved["editable"]
protected = resolved["protected"]
light_actor = resolved["key_light"]
protected_before = actor_state(protected)
if protected_before != request["expected_protected_state_sha256"]:
    fail("protected actor state differs from the rebound request")

operation_results = []
changed = False

# 1. Asset reuse is a catalog selection: verify identity and license before PCG consumes it.
allowed_meshes = []
for asset_path in request["asset"]["asset_paths"]:
    mesh = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not isinstance(mesh, unreal.StaticMesh):
        fail(f"project asset is missing or not a StaticMesh: {asset_path}")
    allowed_meshes.append(mesh.get_path_name())
operation_results.append(
    {
        "operation_id": "asset-reuse",
        "status": "reconciled",
        "evidence": {
            "asset_count": len(allowed_meshes),
            "license_project_owned": request["asset"]["license_policy"] == "project_owned",
            "asset_path": allowed_meshes[0],
        },
    }
)

# 2. Apply the bounded lighting patch.
light = light_actor.get_component_by_class(unreal.LightComponent)
if light is None:
    fail("bound key light has no LightComponent")
lighting_reconciled = (
    abs(float(light.get_editor_property("intensity")) - request["lighting"]["intensity"]) < 1e-6
    and bool(light.get_editor_property("use_temperature"))
    and abs(float(light.get_editor_property("temperature")) - request["lighting"]["temperature_kelvin"]) < 1e-6
)
if not lighting_reconciled:
    light.set_editor_property("intensity", request["lighting"]["intensity"])
    light.set_editor_property("use_temperature", True)
    light.set_editor_property("temperature", request["lighting"]["temperature_kelvin"])
    changed = True
operation_results.append(
    {
        "operation_id": "lighting-patch",
        "status": "reconciled" if lighting_reconciled else "executed",
        "evidence": {
            "intensity": float(light.get_editor_property("intensity")),
            "temperature_kelvin": float(light.get_editor_property("temperature")),
            "use_temperature": bool(light.get_editor_property("use_temperature")),
        },
    }
)

# 3. Bind the content-addressed M8 material and verify its originating request metadata.
material_path = request["material"]["material_instance_path"]
instance = unreal.EditorAssetLibrary.load_asset(material_path)
if not isinstance(instance, unreal.MaterialInstanceConstant):
    fail("bound M8 material instance is missing")
if unreal.EditorAssetLibrary.get_metadata_tag(instance, "ArtFlow.RequestSha256") != request["material"]["pbr_request_sha256"]:
    fail("material instance provenance does not match the M8 request")
mesh_component = target.get_component_by_class(unreal.StaticMeshComponent)
if mesh_component is None:
    fail("editable target has no StaticMeshComponent")
slot = request["material"]["slot_index"]
current_material = mesh_component.get_material(slot)
material_reconciled = current_material is not None and current_material.get_path_name() == material_path
if not material_reconciled:
    mesh_component.set_material(slot, instance)
    changed = True
operation_results.append(
    {
        "operation_id": "material-bind",
        "status": "reconciled" if material_reconciled else "executed",
        "evidence": {
            "slot_index": slot,
            "material_instance_path": instance.get_path_name(),
            "pbr_request_sha256": request["material"]["pbr_request_sha256"],
        },
    }
)

# 4. Reconcile the reviewed PCG component and inspect its real generated instances.
pcg_components = target.get_components_by_class(unreal.PCGComponent)
if len(pcg_components) != 1:
    fail(f"editable target exposes {len(pcg_components)} PCG components; expected one")
pcg_component = pcg_components[0]
graph = pcg_component.get_graph()
if graph is None or graph.get_path_name() != request["pcg"]["reviewed_graph_path"]:
    fail("PCG component is not bound to the reviewed graph")
if int(pcg_component.get_editor_property("seed")) != request["pcg"]["seed"]:
    fail("PCG component seed differs from the reviewed deterministic seed")

instance_count = 0
inside_exclusion = 0
generated_meshes = set()
minimum = request["pcg"]["exclusion_bounds"]["minimum"]
maximum = request["pcg"]["exclusion_bounds"]["maximum"]
for actor in actors:
    for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
        mesh = component.get_editor_property("static_mesh")
        if mesh is None or mesh.get_path_name() not in allowed_meshes:
            continue
        generated_meshes.add(mesh.get_path_name())
        count = component.get_instance_count()
        instance_count += count
        for index in range(count):
            transform = component.get_instance_transform(index, world_space=True)
            location = transform.translation
            if (
                minimum["x"] <= location.x <= maximum["x"]
                and minimum["y"] <= location.y <= maximum["y"]
                and minimum["z"] <= location.z <= maximum["z"]
            ):
                inside_exclusion += 1
if instance_count != request["pcg"]["expected_instance_count"]:
    fail(f"PCG instance budget mismatch: got {instance_count}")
if inside_exclusion:
    fail(f"PCG placed {inside_exclusion} instances inside the protected exclusion bounds")
operation_results.append(
    {
        "operation_id": "pcg-layout",
        "status": "reconciled",
        "evidence": {
            "reviewed_graph_path": graph.get_path_name(),
            "reviewed_graph_sha256": request["pcg"]["reviewed_graph_sha256"],
            "seed": int(pcg_component.get_editor_property("seed")),
            "generated_instance_count": instance_count,
            "instances_inside_exclusion": inside_exclusion,
            "generated_mesh_path": min(generated_meshes),
        },
    }
)

protected_after = actor_state(protected)
if protected_after != protected_before:
    fail("protected actor changed before candidate save")
if changed:
    unreal.EditorLoadingAndSavingUtils.save_map(world, request["candidate_scene_path"])
source_after = sha256_file(source_map)
if source_after != source_before:
    fail("source ArtFlowDemo changed during multi-domain execution")

result = {
    "schema_id": "multi-domain-unreal-apply-result/1",
    "request_id": request["request_id"],
    "request_sha256": request_sha256,
    "status": "reconciled" if all(item["status"] == "reconciled" for item in operation_results) else "staged",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "candidate_scene_path": request["candidate_scene_path"],
    "operation_results": operation_results,
    "material_instance_path": instance.get_path_name(),
    "pcg_graph_path": graph.get_path_name(),
    "generated_instance_count": instance_count,
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
unreal.log(
    f"ARTFLOW_M9_APPLY_RESULT status={result['status']} instances={instance_count} "
    f"material={instance.get_path_name()}"
)
