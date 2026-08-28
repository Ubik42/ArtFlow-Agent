from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from artflow_agent.contracts import SceneChangePlan, SceneDigitalTwin, SceneDryRunReceipt


def _actor(
    actor_id: str,
    guid: str,
    *,
    protected: bool = False,
    editable: bool = True,
    light: bool = False,
    pcg: bool = False,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "actor_id": actor_id,
        "actor_guid": guid,
        "actor_path": f"PersistentLevel.{actor_id}",
        "label": actor_id,
        "class_path": "/Script/Engine.StaticMeshActor",
        "transform": {
            "location": {"x": 0, "y": 0, "z": 0},
            "rotation": {"pitch": 0, "yaw": 0, "roll": 0},
            "scale": {"x": 1, "y": 1, "z": 1},
        },
        "bounds": {
            "minimum": {"x": -50, "y": -50, "z": -50},
            "maximum": {"x": 50, "y": 50, "z": 50},
        },
        "tags": ["ArtFlow.Protected"] if protected else ["ArtFlow.Editable"],
        "data_layers": [],
        "material_slots": [
            {
                "slot_index": 0,
                "slot_name": "Default",
                "material_path": "/Engine/BasicShapes/BasicShapeMaterial",
            }
        ],
        "light": None,
        "pcg_components": [],
        "protected": protected,
        "editable": editable,
        "source_fingerprint": "a" * 64,
    }
    if light:
        payload["class_path"] = "/Script/Engine.DirectionalLight"
        payload["light"] = {
            "light_type": "directional",
            "intensity": 8,
            "color_srgb": [1, 1, 1],
            "use_temperature": False,
            "temperature_kelvin": 6500,
            "cast_shadows": True,
        }
    if pcg:
        payload["pcg_components"] = [
            {
                "component_id": "pcg:scatter",
                "component_path": f"PersistentLevel.{actor_id}.PCG_ArtFlowScatter",
                "graph_path": "/Game/ArtFlow/PCG/PCG_ArtFlowScatter",
                "graph_fingerprint": "b" * 64,
                "exposed_parameters": {"density": 0.35, "asset_set": "demo-rocks"},
                "generation_trigger": "on_demand",
            }
        ]
    return payload


def _twin_payload() -> dict[str, object]:
    return {
        "schema_id": "scene-digital-twin/1",
        "twin_id": "twin-demo-001",
        "source_package_id": "package-demo-001",
        "scene_path": "/Game/ArtFlowDemo",
        "captured_at": datetime(2026, 8, 27, tzinfo=UTC).isoformat(),
        "actors": [
            _actor("protected-altar", "1" * 32, protected=True, editable=False),
            _actor("key-light", "2" * 32, light=True),
            _actor("pcg-volume", "3" * 32, pcg=True),
        ],
        "staging_capabilities": [
            {
                "strategy": "candidate_level",
                "available": True,
                "reason": "The non-World-Partition fixture uses a project-local candidate level.",
            },
            {
                "strategy": "data_layer",
                "available": False,
                "reason": "The fixture does not use World Partition.",
            },
        ],
    }


def _plan_payload(twin: SceneDigitalTwin) -> dict[str, object]:
    common = {
        "expected_source_fingerprints": {},
        "write_scope": {
            "stage_id": "artflow-run-001",
            "asset_root": "/Game/ArtFlow/Generated/run-001",
            "target_actor_ids": [],
        },
        "budget": {
            "max_actor_mutations": 1,
            "max_spawned_actors": 0,
            "max_duration_seconds": 30,
        },
        "cleanup": "restore_staged_properties",
    }
    lighting = {
        **common,
        "operation_id": "lighting-main",
        "operation_type": "set_lighting_rig",
        "depends_on": [],
        "expected_source_fingerprints": {"key-light": "a" * 64},
        "write_scope": {**common["write_scope"], "target_actor_ids": ["key-light"]},
        "idempotency_key": "run-001:lighting-main",
        "validators": [
            {"kind": "protected_fingerprint"},
            {"kind": "light_parameter_bounds"},
            {"kind": "zero_source_mutations"},
        ],
        "target_light_ids": ["key-light"],
        "intensity": 5.5,
        "temperature_kelvin": 4200,
    }
    pcg = {
        **common,
        "operation_id": "pcg-scatter",
        "operation_type": "apply_pcg_layout",
        "depends_on": ["lighting-main"],
        "expected_source_fingerprints": {"pcg-volume": "a" * 64},
        "write_scope": {**common["write_scope"], "target_actor_ids": ["pcg-volume"]},
        "idempotency_key": "run-001:pcg-scatter",
        "budget": {
            "max_actor_mutations": 1,
            "max_spawned_actors": 80,
            "max_duration_seconds": 60,
        },
        "validators": [
            {"kind": "protected_fingerprint"},
            {"kind": "pcg_graph_allowlist"},
            {"kind": "bounds"},
            {"kind": "no_collision"},
            {"kind": "actor_budget"},
            {"kind": "zero_source_mutations"},
        ],
        "cleanup": "delete_generated_actors",
        "component_id": "pcg:scatter",
        "approved_graph_path": "/Game/ArtFlow/PCG/PCG_ArtFlowScatter",
        "graph_parameters": {"density": 0.35, "asset_set": "demo-rocks"},
        "seed": 240827,
    }
    return {
        "schema_id": "scene-change-plan/1",
        "plan_id": "plan-demo-001",
        "twin_id": twin.twin_id,
        "twin_sha256": twin.canonical_sha256(),
        "created_at": datetime(2026, 8, 27, tzinfo=UTC).isoformat(),
        "operations": [lighting, pcg],
    }


def test_scene_digital_twin_validates_real_3d_facts_and_authority() -> None:
    twin = SceneDigitalTwin.model_validate(_twin_payload())

    assert len(twin.actors) == 3
    assert twin.actors[1].light is not None
    assert twin.actors[2].pcg_components[0].exposed_parameters["density"] == 0.35
    assert len(twin.canonical_sha256()) == 64

    invalid = _twin_payload()
    invalid["actors"][0]["editable"] = True  # type: ignore[index]
    with pytest.raises(ValidationError, match="protected actors cannot be marked editable"):
        SceneDigitalTwin.model_validate(invalid)


@pytest.mark.parametrize("mutation, message", [
    ("duplicate_id", "actor IDs must be unique"),
    ("invalid_bounds", "bounds minimum.x"),
    ("missing_fingerprint", "source_fingerprint"),
])
def test_scene_digital_twin_rejects_cross_field_corruption(
    mutation: str, message: str
) -> None:
    payload = _twin_payload()
    if mutation == "duplicate_id":
        payload["actors"][1]["actor_id"] = "protected-altar"  # type: ignore[index]
    elif mutation == "invalid_bounds":
        payload["actors"][0]["bounds"]["minimum"]["x"] = 100  # type: ignore[index]
    else:
        del payload["actors"][0]["source_fingerprint"]  # type: ignore[index]

    with pytest.raises(ValidationError, match=message):
        SceneDigitalTwin.model_validate(payload)


def test_scene_change_plan_accepts_only_typed_lighting_and_pcg_dag() -> None:
    twin = SceneDigitalTwin.model_validate(_twin_payload())
    plan = SceneChangePlan.model_validate(_plan_payload(twin))

    assert [item.operation_type for item in plan.operations] == [
        "set_lighting_rig",
        "apply_pcg_layout",
    ]
    assert plan.operations[1].seed == 240827  # type: ignore[union-attr]
    assert len(plan.canonical_sha256()) == 64


def test_scene_change_plan_rejects_unknown_script_and_cycles() -> None:
    twin = SceneDigitalTwin.model_validate(_twin_payload())
    payload = _plan_payload(twin)
    payload["operations"][0]["python"] = "unreal.EditorLevelLibrary.save_current_level()"  # type: ignore[index]
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SceneChangePlan.model_validate(payload)

    payload = _plan_payload(twin)
    payload["operations"][0]["operation_type"] = "execute_python"  # type: ignore[index]
    with pytest.raises(ValidationError, match="union_tag_invalid"):
        SceneChangePlan.model_validate(payload)

    payload = _plan_payload(twin)
    payload["operations"][0]["depends_on"] = ["pcg-scatter"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="must be acyclic"):
        SceneChangePlan.model_validate(payload)


def test_dry_run_receipt_proves_zero_committed_mutations() -> None:
    twin = SceneDigitalTwin.model_validate(_twin_payload())
    plan = SceneChangePlan.model_validate(_plan_payload(twin))
    scene_hash = "f" * 64
    receipt = SceneDryRunReceipt(
        receipt_id="dry-run-001",
        twin_id=twin.twin_id,
        twin_sha256=twin.canonical_sha256(),
        plan_id=plan.plan_id,
        plan_sha256=plan.canonical_sha256(),
        source_scene_path="/Game/ArtFlowDemo",
        source_scene_fingerprint_before=scene_hash,
        source_scene_fingerprint_after=scene_hash,
        staging_strategy="candidate_level",
        stage_id="artflow-run-001",
        planned_operations=[
            {
                "operation_id": "lighting-main",
                "operation_type": "set_lighting_rig",
                "target_ids": ["key-light"],
                "parameter_names": ["intensity", "temperature_kelvin"],
            },
            {
                "operation_id": "pcg-scatter",
                "operation_type": "apply_pcg_layout",
                "target_ids": ["pcg:scatter"],
                "parameter_names": ["density", "asset_set", "seed"],
            },
        ],
        protected_invariants={"protected-altar": "a" * 64},
        created_at=datetime(2026, 8, 27, tzinfo=UTC),
    )
    assert receipt.dry_run is True
    assert receipt.committed_mutation_count == 0

    with pytest.raises(ValidationError, match="fingerprint must remain unchanged"):
        SceneDryRunReceipt.model_validate(
            receipt.model_copy(
                update={"source_scene_fingerprint_after": "e" * 64}
            ).model_dump(mode="json")
        )
