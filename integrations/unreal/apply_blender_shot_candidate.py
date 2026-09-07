from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import unreal


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow shot return failed: {message}")


def find_actor(actors: list[unreal.Actor], label: str) -> unreal.Actor | None:
    return next((actor for actor in actors if actor.get_actor_label() == label), None)


def apply_directional_light(
    actor: unreal.DirectionalLight,
    *,
    label: str,
    role: str,
    rig: dict[str, object],
    request_id: str,
) -> None:
    rotation = rig["rotation_deg"]
    actor.set_actor_label(label)
    actor.set_actor_rotation(
        unreal.Rotator(pitch=rotation[0], yaw=rotation[1], roll=rotation[2]), False
    )
    actor.tags = ["ArtFlow.DCCShot", request_id, f"ArtFlow.LightRole.{role}"]
    component = actor.get_editor_property("directional_light_component")
    component.set_editor_property("intensity", rig["intensity_lux"])
    component.set_editor_property("use_temperature", True)
    component.set_editor_property("temperature", rig["temperature_kelvin"])
    component.set_editor_property("cast_shadows", rig["cast_shadows"])


repo_root = Path(__file__).resolve().parents[2]
evidence_root = repo_root / "artifacts/goal/m23-s5-camera-light"
layout_root = repo_root / "artifacts/goal/m23-s4-geometry-layout"
request = json.loads((evidence_root / "shot-request.json").read_text(encoding="utf-8"))
shot_receipt = json.loads((evidence_root / "shot-receipt.json").read_text(encoding="utf-8"))
source = json.loads(
    (evidence_root / "unreal-camera-light-source.json").read_text(encoding="utf-8")
)
layout_return = json.loads(
    (layout_root / "unreal-return-receipt.json").read_text(encoding="utf-8")
)
if request.get("schema_id") != "artflow-blender-shot-request/1":
    fail("unsupported shot request schema")
if shot_receipt.get("request_sha256") != request.get("request_sha256"):
    fail("Blender shot receipt does not match the request")
if request.get("source_receipt_sha256") != source.get("receipt_sha256"):
    fail("Unreal camera-light facts do not match the shot request")
if request.get("layout_receipt_sha256") != layout_return.get("blender_receipt_sha256"):
    fail("Geometry Nodes candidate does not match the shot request")

project_root = Path(unreal.Paths.project_dir()).resolve()
source_map = project_root / "Content/ArtFlowDemo.umap"
source_before = file_sha256(source_map)
if source_before != request["source_level_sha256"]:
    fail("source level changed after the shot request was compiled")

identity = request["request_sha256"][:12]
source_candidate = layout_return["candidate_scene_path"]
candidate_name = f"Shot_B_{identity}"
candidate_package = f"/Game/ArtFlow/Sessions/AF_dc31f6ed0f4e/Candidates/{candidate_name}"
candidate_object = f"{candidate_package}.{candidate_name}"
candidate_reconciled = unreal.EditorAssetLibrary.does_asset_exist(candidate_object)
if not candidate_reconciled:
    world_asset = unreal.EditorAssetLibrary.duplicate_asset(source_candidate, candidate_package)
    if world_asset is None:
        fail("could not duplicate the Geometry Nodes candidate")
    unreal.EditorAssetLibrary.save_loaded_asset(world_asset, only_if_is_dirty=False)
    del world_asset
    unreal.SystemLibrary.collect_garbage()

world = unreal.EditorLoadingAndSavingUtils.load_map(candidate_package)
if world is None:
    fail("could not load the isolated shot candidate")
actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = actor_subsystem.get_all_level_actors()

camera_fact = request["camera"]
camera = find_actor(actors, camera_fact["label"])
if not isinstance(camera, unreal.CameraActor):
    fail(f"registered camera is missing: {camera_fact['label']}")
camera_location = unreal.Vector(*camera_fact["location_cm"])
camera_rotation = unreal.Rotator(
    pitch=camera_fact["rotation_deg"][0],
    yaw=camera_fact["rotation_deg"][1],
    roll=camera_fact["rotation_deg"][2],
)
camera.set_actor_location(camera_location, False, False)
camera.set_actor_rotation(camera_rotation, False)
camera_component = camera.get_editor_property("camera_component")
camera_component.set_editor_property("field_of_view", camera_fact["horizontal_fov_deg"])
camera_component.set_editor_property("aspect_ratio", camera_fact["aspect_ratio"])

rig_by_role = {item["role"]: item for item in request["proposed_rig"]}
light_bindings = (
    ("key", "ArtFlow_KeyLight"),
    ("fill", "DirectionalLight"),
    ("rim", "ArtFlow_DCC_RimLight"),
)
rim_reconciled = isinstance(find_actor(actors, "ArtFlow_DCC_RimLight"), unreal.DirectionalLight)
applied_lights: list[dict[str, object]] = []
for role, label in light_bindings:
    actor = find_actor(actors, label)
    if actor is None and role == "rim":
        actor = actor_subsystem.spawn_actor_from_class(
            unreal.DirectionalLight, unreal.Vector(), unreal.Rotator()
        )
    if not isinstance(actor, unreal.DirectionalLight):
        fail(f"registered directional light is missing: {label}")
    rig = rig_by_role[role]
    apply_directional_light(
        actor, label=label, role=role, rig=rig, request_id=request["request_id"]
    )
    applied_lights.append({"label": label, "role": role, **rig})

unreal.EditorLoadingAndSavingUtils.save_map(world, candidate_package)

screenshot_path = evidence_root / "unreal-shot-candidate.png"
if screenshot_path.is_file():
    screenshot_path.unlink()
unreal.AutomationLibrary.take_high_res_screenshot(
    1280, 720, str(screenshot_path), camera, False, False
)
source_after = file_sha256(source_map)
if source_after != source_before:
    fail("source level changed while returning the Blender shot")

camera_location_error = (camera.get_actor_location() - camera_location).length()
result = {
    "schema_id": "artflow-unreal-shot-return-receipt/1",
    "request_id": request["request_id"],
    "request_sha256": request["request_sha256"],
    "blender_shot_receipt_sha256": shot_receipt["receipt_sha256"],
    "status": "reconciled" if candidate_reconciled and rim_reconciled else "imported",
    "engine_version": unreal.SystemLibrary.get_engine_version(),
    "source_candidate_scene_path": source_candidate,
    "candidate_scene_path": candidate_package,
    "camera_label": camera.get_actor_label(),
    "camera_horizontal_fov_deg": camera_component.get_editor_property("field_of_view"),
    "camera_location_error_cm": camera_location_error,
    "applied_lights": applied_lights,
    "source_level_sha256_before": source_before,
    "source_level_sha256_after": source_after,
    "screenshot_path": screenshot_path.name,
    "screenshot_sha256": None,
    "capture_status": "requested",
    "duplicate_side_effect_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical_sha256(result)
(evidence_root / "unreal-shot-return-receipt.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
unreal.log(
    "ARTFLOW_SHOT_RETURN_SUBMITTED "
    f"status={result['status']} candidate={candidate_package} lights={len(applied_lights)}"
)
