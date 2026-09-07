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


def transform_payload(actor: unreal.Actor) -> dict[str, object]:
    location = actor.get_actor_location()
    rotation = actor.get_actor_rotation()
    return {
        "location_cm": [location.x, location.y, location.z],
        "rotation_deg": [rotation.pitch, rotation.yaw, rotation.roll],
    }


repo_root = Path(__file__).resolve().parents[2]
output_root = repo_root / "artifacts/goal/m23-s5-camera-light"
output_root.mkdir(parents=True, exist_ok=True)
project_root = Path(unreal.Paths.project_dir()).resolve()
source_map = project_root / "Content/ArtFlowDemo.umap"
source_sha256 = file_sha256(source_map)
world = unreal.EditorLoadingAndSavingUtils.load_map("/Game/ArtFlowDemo")
if world is None:
    raise RuntimeError("ARTFLOW_SHOT_EXPORT_FAILED: cannot load source level")
actors = unreal.get_editor_subsystem(unreal.EditorActorSubsystem).get_all_level_actors()
camera = next((actor for actor in actors if actor.get_actor_label() == "ArtFlow_Camera"), None)
if not isinstance(camera, unreal.CameraActor):
    raise TypeError("ARTFLOW_SHOT_EXPORT_FAILED: registered camera is missing")
camera_component = camera.get_editor_property("camera_component")

lights = []
for label in ("ArtFlow_KeyLight", "DirectionalLight"):
    actor = next((item for item in actors if item.get_actor_label() == label), None)
    if not isinstance(actor, unreal.DirectionalLight):
        raise TypeError(f"ARTFLOW_SHOT_EXPORT_FAILED: registered light {label} is missing")
    component = actor.get_editor_property("directional_light_component")
    lights.append(
        {
            "label": label,
            **transform_payload(actor),
            "intensity_lux": component.get_editor_property("intensity"),
            "temperature_kelvin": component.get_editor_property("temperature"),
            "use_temperature": component.get_editor_property("use_temperature"),
            "cast_shadows": component.get_editor_property("cast_shadows"),
        }
    )

result = {
    "schema_id": "artflow-unreal-camera-light-source/1",
    "session_id": "scene-session-dc31f6ed0f4e",
    "session_sha256": "dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
    "source_scene": "/Game/ArtFlowDemo",
    "source_level_sha256": source_sha256,
    "camera": {
        "label": "ArtFlow_Camera",
        **transform_payload(camera),
        "horizontal_fov_deg": camera_component.get_editor_property("field_of_view"),
        "aspect_ratio": camera_component.get_editor_property("aspect_ratio"),
    },
    "directional_lights": lights,
    "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical_sha256(result)
(output_root / "unreal-camera-light-source.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
unreal.log(
    f"ARTFLOW_SHOT_SOURCE_EXPORTED camera={camera.get_actor_label()} lights={len(lights)} source={source_sha256[:12]}"
)
