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
    raise RuntimeError(f"ArtFlow published variant review failed closed: {message}")


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
        fail("current review requires a localhost origin and registered run identity")
    request = request_json(
        f"{current_origin}/api/agent/runs/{current_run}/current-variant/review-request"
    )
    result_path = (
        Path(unreal.Paths.project_saved_dir()).resolve()
        / "ArtFlowSceneBridge"
        / "CurrentVariant"
        / request["review_id"]
        / "review-receipt.json"
    )
    allowed_result_root = Path(unreal.Paths.project_dir()).resolve()
else:
    repo_root_value = os.environ.get("ARTFLOW_REPO_ROOT")
    if not repo_root_value:
        fail("legacy review requires the repository root")
    repo_root = Path(repo_root_value).resolve()
    request_path = Path(os.environ["ARTFLOW_SCENE_REVIEW_REQUEST"]).resolve()
    result_path = Path(os.environ["ARTFLOW_SCENE_REVIEW_RESULT"]).resolve()
    if not request_path.is_relative_to(repo_root):
        fail("request escaped the repository")
    request = json.loads(request_path.read_text(encoding="utf-8"))
    allowed_result_root = repo_root
if not result_path.is_relative_to(allowed_result_root):
    fail("result escaped the repository")
if request.get("schema_id") != "artflow-scene-variant-review-request/1":
    fail("unsupported review request schema")
payload = {
    key: value
    for key, value in request.items()
    if key not in {"schema_id", "review_id", "review_sha256", "idempotency_key"}
}
review_sha = canonical_sha256(payload)
if request.get("review_sha256") != review_sha:
    fail("review request fingerprint mismatch")
if request.get("review_id") != f"scene-review-{review_sha[:16]}":
    fail("review request id mismatch")
if request.get("idempotency_key") != f"scene-review:{review_sha}":
    fail("review idempotency key mismatch")
published_scene = request["published_scene"]
match = re.fullmatch(
    r"/Game/ArtFlow/Published/AF_[a-f0-9]{12}/V_([a-f0-9]{12})",
    published_scene,
)
if match is None or match.group(1) != request["content_identity_sha256"][:12]:
    fail("review request escaped the registered Published variant")
if request.get("source_scene") != "/Game/ArtFlowDemo":
    fail("review request references an unsupported source level")

project_root = Path(unreal.Paths.project_dir()).resolve()
content_root = project_root / "Content"
source_file = content_root / "ArtFlowDemo.umap"
published_file = content_root / Path(published_scene.removeprefix("/Game/") + ".umap")
if not source_file.is_file() or file_sha256(source_file) != request["source_level_sha256"]:
    fail("source level bytes differ from the adoption decision")
if not published_file.is_file() or file_sha256(published_file) != request["published_level_sha256"]:
    fail("published level bytes differ from the publish receipt")
source_before = file_sha256(source_file)

if current_origin and current_run and not unreal.EditorLoadingAndSavingUtils.load_map(published_scene):
    fail("Unreal could not open the exact Published variant for review")

world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
if world is None or world.get_outermost().get_name() != published_scene:
    fail("Unreal did not open the exact Published variant from the review request")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()


def by_label(label: str) -> unreal.Actor:
    actor = next((item for item in actors if item.get_actor_label() == label), None)
    if actor is None:
        fail(f"required actor is missing: {label}")
    return actor


protected = by_label("Protected_Blockout")
editable = by_label("Editable_Form")
editable_component = editable.get_component_by_class(unreal.StaticMeshComponent)
if editable_component is None or editable_component.get_material(0) is None:
    fail("editable material binding is missing")
facts = {
    "protected_state_sha256": actor_state(protected),
    "material_path": editable_component.get_material(0).get_path_name(),
    "generated_instance_count": sum(
        component.get_instance_count()
        for actor in actors
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
        if "ArtFlow.Generated" in {str(tag) for tag in component.component_tags}
    ),
}
if facts != {
    "protected_state_sha256": request["expected_protected_state_sha256"],
    "material_path": request["expected_material_path"],
    "generated_instance_count": request["expected_instance_count"],
}:
    fail("opened Published variant differs from the review request")
source_after = file_sha256(source_file)
if source_after != source_before:
    fail("review changed the source level")

ledger_dir = project_root / "Saved" / "ArtFlowSceneBridge" / "PublishedReview"
ledger_path = ledger_dir / f"{request['review_id']}.json"
reconciled = ledger_path.is_file()
if reconciled:
    prior = json.loads(ledger_path.read_text(encoding="utf-8"))
    if (
        prior.get("review_sha256") != review_sha
        or prior.get("published_level_sha256") != request["published_level_sha256"]
    ):
        fail("existing review ledger belongs to different Published content")

result = {
    "schema_id": "artflow-scene-variant-review-receipt/1",
    "review_id": request["review_id"],
    "review_sha256": review_sha,
    "status": "reconciled" if reconciled else "inspected",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "published_scene": published_scene,
    "published_level_sha256": request["published_level_sha256"],
    "source_level_sha256_before": source_before,
    "source_level_sha256_after": source_after,
    **facts,
    "source_save_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical_sha256(result)
encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
for path in (ledger_path, result_path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)
if current_origin and current_run:
    request_json(
        f"{current_origin}/api/agent/runs/{current_run}/current-variant/review-receipt",
        payload=result,
    )
unreal.log(
    f"ARTFLOW_SCENE_REVIEW status={result['status']} path={published_scene} "
    f"instances={facts['generated_instance_count']}"
)

