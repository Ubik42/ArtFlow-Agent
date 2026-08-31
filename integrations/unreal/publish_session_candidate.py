from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
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
    raise RuntimeError(f"ArtFlow Session publish failed closed: {message}")


def request_json(url: str, *, payload: dict[str, object] | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"} if body is not None else {},
        method="POST" if body is not None else "GET",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


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


def inspect_loaded_scene() -> dict[str, object]:
    actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()

    def by_label(label: str) -> unreal.Actor:
        actor = next((item for item in actors if item.get_actor_label() == label), None)
        if actor is None:
            fail(f"required actor is missing: {label}")
        return actor

    protected = by_label("Protected_Blockout")
    editable = by_label("Editable_Form")
    component = editable.get_component_by_class(unreal.StaticMeshComponent)
    if component is None or component.get_material(0) is None:
        fail("editable material binding is missing")
    instance_count = sum(
        component.get_instance_count()
        for actor in actors
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
        if "ArtFlow.Generated" in {str(tag) for tag in component.component_tags}
    )
    return {
        "protected_state_sha256": actor_state(protected),
        "material_path": component.get_material(0).get_path_name(),
        "generated_instance_count": instance_count,
    }


repo_root = Path(os.environ["ARTFLOW_REPO_ROOT"]).resolve()
current_origin = os.environ.get("ARTFLOW_CURRENT_VARIANT_ORIGIN")
current_run = os.environ.get("ARTFLOW_CURRENT_VARIANT_RUN")
if current_origin or current_run:
    if (
        not current_origin
        or not current_run
        or not current_origin.startswith("http://127.0.0.1:")
        or "/" in current_run
        or "\\" in current_run
    ):
        fail("current publish requires a localhost origin and registered run identity")
    request = request_json(
        f"{current_origin}/api/agent/runs/{current_run}/current-variant/publish-request"
    )
    result_path = (
        Path(unreal.Paths.project_saved_dir()).resolve()
        / "ArtFlowSceneBridge"
        / "CurrentVariant"
        / request["request_id"]
        / "publish-receipt.json"
    )
else:
    request_path = Path(os.environ["ARTFLOW_SCENE_PUBLISH_REQUEST"]).resolve()
    result_path = Path(os.environ["ARTFLOW_SCENE_PUBLISH_RESULT"]).resolve()
    if not request_path.is_relative_to(repo_root):
        fail("request escaped the repository")
    request = json.loads(request_path.read_text(encoding="utf-8"))
if not result_path.is_relative_to(repo_root):
    fail("result escaped the repository")
if request.get("schema_id") != "artflow-scene-variant-publish-request/1":
    fail("unsupported request schema")
request_payload = {
    key: value
    for key, value in request.items()
    if key not in {"schema_id", "request_id", "request_sha256", "idempotency_key"}
}
request_sha = canonical_sha256(request_payload)
if request.get("request_sha256") != request_sha:
    fail("publish request fingerprint mismatch")
if request.get("request_id") != f"scene-publish-{request_sha[:16]}":
    fail("publish request id mismatch")
if request.get("idempotency_key") != f"scene-publish:{request_sha}":
    fail("publish idempotency key mismatch")

decision = request.get("decision", {})
if decision.get("schema_id") != "artflow-scene-adoption-decision/1":
    fail("unsupported adoption decision schema")
decision_payload = {
    key: value
    for key, value in decision.items()
    if key not in {"schema_id", "decision_id", "decision_sha256"}
}
decision_sha = canonical_sha256(decision_payload)
if decision.get("decision_sha256") != decision_sha:
    fail("adoption decision fingerprint mismatch")
if decision.get("decision_id") != f"scene-adoption-{decision_sha[:16]}":
    fail("adoption decision id mismatch")
if (
    decision.get("action") != "publish"
    or decision.get("orchestrator") != "codex"
    or decision.get("policy_version") != "scene-disposition-policy/1"
):
    fail("adoption authority or policy is not registered")

identity = canonical_sha256(
    {
        "evaluation_sha256": decision["evaluation_sha256"],
        "plan_sha256": decision["plan_sha256"],
        "execution_receipt_sha256": decision["execution_receipt_sha256"],
        "source_level_sha256": decision["source_level_sha256"],
        "candidate_level_sha256": decision["candidate_level_sha256"],
    }
)
if decision.get("content_identity_sha256") != identity:
    fail("adoption content identity mismatch")
candidate_scene = decision["candidate_scene"]
published_scene = decision["published_scene"]
candidate_match = re.fullmatch(
    r"/Game/ArtFlow/Sessions/AF_([a-f0-9]{12})/Candidates/C_([a-f0-9]{12})",
    candidate_scene,
)
if candidate_match is None:
    fail("candidate escaped the content-addressed Session namespace")
expected_published = (
    f"/Game/ArtFlow/Published/AF_{candidate_match.group(1)}/V_{identity[:12]}"
)
if published_scene != expected_published:
    fail("published scene escaped the content-addressed Published namespace")
if decision.get("source_scene") != "/Game/ArtFlowDemo":
    fail("publish request references an unsupported source level")

project_root = Path(unreal.Paths.project_dir()).resolve()
content_root = project_root / "Content"
source_file = content_root / "ArtFlowDemo.umap"
candidate_file = content_root / Path(candidate_scene.removeprefix("/Game/") + ".umap")
published_file = content_root / Path(published_scene.removeprefix("/Game/") + ".umap")
source_before = file_sha256(source_file)
if source_before != decision["source_level_sha256"]:
    fail("source level fingerprint is stale")
if not candidate_file.is_file() or file_sha256(candidate_file) != decision["candidate_level_sha256"]:
    fail("candidate bytes changed after adoption")

candidate_world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_scene)
if not candidate_world:
    fail("candidate scene could not be loaded")
candidate_facts = inspect_loaded_scene()
if candidate_facts["protected_state_sha256"] != request["expected_protected_state_sha256"]:
    fail("candidate protected state changed after evaluation")
if candidate_facts["material_path"] != request["expected_material_path"]:
    fail("candidate material changed after evaluation")
if candidate_facts["generated_instance_count"] != request["expected_instance_count"]:
    fail("candidate PCG instance count changed after evaluation")
del candidate_world
unreal.SystemLibrary.collect_garbage()

metadata_key = "ArtFlow.PublishRequestSha256"
reconciled = unreal.EditorAssetLibrary.does_asset_exist(published_scene)
if reconciled:
    published_asset = unreal.EditorAssetLibrary.load_asset(published_scene)
    if published_asset is None:
        fail("published scene exists but cannot be loaded")
    if unreal.EditorAssetLibrary.get_metadata_tag(published_asset, metadata_key) != request_sha:
        fail("published destination belongs to another disposition request")
else:
    published_asset = unreal.EditorAssetLibrary.duplicate_asset(candidate_scene, published_scene)
    if published_asset is None:
        fail("candidate scene could not be duplicated into the Published namespace")
    unreal.EditorAssetLibrary.set_metadata_tag(published_asset, metadata_key, request_sha)
    unreal.EditorAssetLibrary.set_metadata_tag(
        published_asset, "ArtFlow.AdoptionDecisionSha256", decision_sha
    )
    unreal.EditorAssetLibrary.set_metadata_tag(
        published_asset, "ArtFlow.EvaluationSha256", decision["evaluation_sha256"]
    )
    unreal.EditorAssetLibrary.set_metadata_tag(
        published_asset, "ArtFlow.CandidateLevelSha256", decision["candidate_level_sha256"]
    )
    if not unreal.EditorAssetLibrary.save_asset(published_scene, only_if_is_dirty=False):
        fail("published scene could not be saved")

# Map assets are UWorld instances. Keeping either Python proxy alive while loading
# another map makes UE 5.8 correctly abort on a leaked World/package reference.
del published_asset
unreal.SystemLibrary.collect_garbage()

if not published_file.is_file():
    fail("published map file is missing after publication")
published_world = unreal.EditorLoadingAndSavingUtils.load_map(published_scene)
if not published_world:
    fail("published scene could not be loaded for verification")
published_facts = inspect_loaded_scene()
del published_world
if published_facts != candidate_facts:
    fail("published scene technical facts differ from the adopted candidate")
source_after = file_sha256(source_file)
if source_after != source_before:
    fail("publication changed the source level")

result = {
    "schema_id": "artflow-scene-variant-publish-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request_sha,
    "decision_sha256": decision_sha,
    "status": "reconciled" if reconciled else "published",
    "candidate_scene": candidate_scene,
    "candidate_level_sha256": decision["candidate_level_sha256"],
    "published_scene": published_scene,
    "published_level_sha256": file_sha256(published_file),
    "source_level_sha256_before": source_before,
    "source_level_sha256_after": source_after,
    "protected_state_sha256": published_facts["protected_state_sha256"],
    "material_path": published_facts["material_path"],
    "generated_instance_count": published_facts["generated_instance_count"],
    "duplicate_side_effect_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical_sha256(result)
result_path.parent.mkdir(parents=True, exist_ok=True)
temporary = result_path.with_suffix(result_path.suffix + ".tmp")
temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
temporary.replace(result_path)
if current_origin and current_run:
    request_json(
        f"{current_origin}/api/agent/runs/{current_run}/current-variant/publish-receipt",
        payload=result,
    )
unreal.log(
    f"ARTFLOW_SESSION_PUBLISH status={result['status']} path={published_scene} "
    f"instances={published_facts['generated_instance_count']}"
)
