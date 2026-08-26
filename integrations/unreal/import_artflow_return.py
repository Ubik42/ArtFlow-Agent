from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import unreal


def canonical_sha256(payload: dict, field: str) -> str:
    value = dict(payload)
    value.pop(field, None)
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow return failed closed: {message}")


request_path = Path(os.environ["ARTFLOW_RETURN_REQUEST"]).resolve()
receipt_path = Path(os.environ["ARTFLOW_RETURN_RECEIPT"]).resolve()
repo_root = Path(os.environ["ARTFLOW_REPO_ROOT"]).resolve()
if not request_path.is_relative_to(repo_root) or not receipt_path.is_relative_to(repo_root):
    fail("request or receipt path escaped the ArtFlow repository")
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "artflow-unreal-return-request/1":
    fail("unsupported request schema")
if canonical_sha256(request, "request_sha256") != request.get("request_sha256"):
    fail("request content hash mismatch")
if request.get("authority_scope") != "project_local_unreal_fixture":
    fail("request authority is not project-local")
if request.get("destination_scene_path") != "/Game/ArtFlowDemo":
    fail("only the fixed ArtFlowDemo scene is writable")
destination = request.get("destination_asset_path", "")
if not destination.startswith("/Game/ArtFlow/Returns/T_ArtFlow_"):
    fail("destination escaped the ArtFlow return namespace")
source_path = (repo_root / request["source"]["path"]).resolve()
if not source_path.is_relative_to(repo_root) or not source_path.is_file():
    fail("source artifact is missing or escaped the repository")
if sha256_file(source_path) != request["source"]["sha256"]:
    fail("source artifact hash mismatch")

asset_name = destination.rsplit("/", 1)[-1]
asset_dir = destination.rsplit("/", 1)[0]
object_path = f"{destination}.{asset_name}"
existing = (
    unreal.EditorAssetLibrary.load_asset(object_path)
    if unreal.EditorAssetLibrary.does_asset_exist(object_path)
    else None
)
if existing:
    recorded_hash = unreal.EditorAssetLibrary.get_metadata_tag(existing, "ArtFlow.SourceSha256")
    if recorded_hash != request["source"]["sha256"]:
        fail("an unrelated asset already occupies the deterministic destination")
    texture = existing
else:
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", str(source_path))
    task.set_editor_property("destination_path", asset_dir)
    task.set_editor_property("destination_name", asset_name)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", False)
    task.set_editor_property("save", True)
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    texture = unreal.EditorAssetLibrary.load_asset(object_path)
    if not texture:
        fail("Unreal did not create the requested texture asset")

metadata = {
    "ArtFlow.RunId": request["run_id"],
    "ArtFlow.ImportId": request["import_id"],
    "ArtFlow.SourceSha256": request["source"]["sha256"],
    "ArtFlow.RequestSha256": request["request_sha256"],
    "ArtFlow.AdoptionSha256": request["adoption_decision_sha256"],
    "ArtFlow.TribunalSha256": request["tribunal_sha256"],
}
for key, value in metadata.items():
    unreal.EditorAssetLibrary.set_metadata_tag(texture, key, value)
unreal.EditorAssetLibrary.save_loaded_asset(texture, only_if_is_dirty=False)

material_name = f"M_ArtFlow_{request['import_id'].removeprefix('return-')}"
material_path = f"{asset_dir}/{material_name}.{material_name}"
material = (
    unreal.EditorAssetLibrary.load_asset(material_path)
    if unreal.EditorAssetLibrary.does_asset_exist(material_path)
    else None
)
if material is None:
    material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        material_name, asset_dir, unreal.Material, unreal.MaterialFactoryNew()
    )
    if material is None:
        fail("could not create the return preview material")
    material.set_editor_property("two_sided", True)
    sample = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSample, -300, 0
    )
    sample.set_editor_property("texture", texture)
    if not unreal.MaterialEditingLibrary.connect_material_property(
        sample, "RGB", unreal.MaterialProperty.MP_EMISSIVE_COLOR
    ):
        fail("could not bind the returned texture to its preview material")
    unreal.MaterialEditingLibrary.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material, only_if_is_dirty=False)

world = unreal.EditorLoadingAndSavingUtils.load_map(request["destination_scene_path"])
if not world:
    fail("ArtFlowDemo could not be loaded")
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
binding_label = f"ArtFlow_Return_{request['import_id'][-8:]}"
actor = next(
    (item for item in actor_subsystem.get_all_level_actors() if item.get_actor_label() == binding_label),
    None,
)
if actor is None:
    actor = actor_subsystem.spawn_actor_from_class(
        unreal.StaticMeshActor, unreal.Vector(0.0, 390.0, 120.0), unreal.Rotator()
    )
    if actor is None:
        fail("could not create the return binding actor")
actor.set_actor_label(binding_label)
actor.set_actor_location(unreal.Vector(150.0, 360.0, 260.0), False, False)
actor.set_actor_rotation(unreal.Rotator(0.0, 90.0, 90.0), False)
actor.set_actor_scale3d(unreal.Vector(3.4, 6.0, 3.4))
plane = unreal.EditorAssetLibrary.load_asset("/Engine/BasicShapes/Plane.Plane")
actor.static_mesh_component.set_static_mesh(plane)
actor.static_mesh_component.set_material(0, material)
actor.tags = ["ArtFlow.Return", request["import_id"], request["source"]["sha256"][:16]]
unreal.EditorLoadingAndSavingUtils.save_map(world, request["destination_scene_path"])

previous_receipt = None
if receipt_path.is_file():
    candidate_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        candidate_receipt.get("request_sha256") == request["request_sha256"]
        and canonical_sha256(candidate_receipt, "receipt_sha256")
        == candidate_receipt.get("receipt_sha256")
    ):
        previous_receipt = candidate_receipt
receipt = {
    "schema_id": "artflow-unreal-return-receipt/1",
    "import_id": request["import_id"],
    "request_sha256": request["request_sha256"],
    "status": "imported",
    "source_sha256": request["source"]["sha256"],
    "imported_asset_path": object_path,
    "bound_scene_path": request["destination_scene_path"],
    "binding_actor_label": binding_label,
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "metadata": metadata,
    "completed_at": (
        previous_receipt["completed_at"]
        if previous_receipt
        else datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    ),
    "receipt_sha256": "0" * 64,
}
receipt["receipt_sha256"] = canonical_sha256(receipt, "receipt_sha256")
receipt_path.parent.mkdir(parents=True, exist_ok=True)
temporary = receipt_path.with_suffix(".json.part")
temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
temporary.replace(receipt_path)
unreal.log(
    f"ARTFLOW_RETURN_RESULT import={request['import_id']} receipt={receipt['receipt_sha256']}"
)
