from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SHA256_PATTERN = r"^[0-9a-f]{64}$"
UNREAL_OBJECT_PATH_PATTERN = r"^/(?:Game|Engine)/[A-Za-z0-9_./-]+$"
ARTFLOW_ASSET_ROOT_PATTERN = r"^/Game/ArtFlow/Generated/[a-z0-9][a-z0-9._-]{2,119}$"


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Vector3(StrictContract):
    x: float
    y: float
    z: float


class Rotator(StrictContract):
    pitch: float
    yaw: float
    roll: float


class TransformFact(StrictContract):
    location: Vector3
    rotation: Rotator
    scale: Vector3

    @model_validator(mode="after")
    def reject_zero_scale(self) -> TransformFact:
        if any(abs(value) < 1e-9 for value in (self.scale.x, self.scale.y, self.scale.z)):
            raise ValueError("transform scale components must be non-zero")
        return self


class BoundsFact(StrictContract):
    minimum: Vector3
    maximum: Vector3

    @model_validator(mode="after")
    def require_ordered_bounds(self) -> BoundsFact:
        for axis in ("x", "y", "z"):
            if getattr(self.minimum, axis) > getattr(self.maximum, axis):
                raise ValueError(f"bounds minimum.{axis} must not exceed maximum.{axis}")
        return self


class MaterialSlotFact(StrictContract):
    slot_index: int = Field(ge=0, le=255)
    slot_name: str = Field(min_length=1, max_length=120)
    material_path: str = Field(pattern=UNREAL_OBJECT_PATH_PATTERN)


class LightFact(StrictContract):
    light_type: Literal["directional", "sky", "point", "spot", "rect"]
    intensity: float = Field(ge=0)
    color_srgb: list[float] = Field(min_length=3, max_length=3)
    use_temperature: bool
    temperature_kelvin: float = Field(ge=1000, le=20000)
    cast_shadows: bool

    @field_validator("color_srgb")
    @classmethod
    def validate_color(cls, value: list[float]) -> list[float]:
        if any(channel < 0 or channel > 1 for channel in value):
            raise ValueError("light color channels must be between 0 and 1")
        return value


PrimitiveParameter = bool | int | float | str


class PCGComponentFact(StrictContract):
    component_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,159}$")
    component_path: str = Field(min_length=1, max_length=512)
    graph_path: str = Field(pattern=UNREAL_OBJECT_PATH_PATTERN)
    graph_fingerprint: str = Field(pattern=SHA256_PATTERN)
    exposed_parameters: dict[str, PrimitiveParameter] = Field(default_factory=dict, max_length=64)
    generation_trigger: Literal["on_demand", "generate_on_load", "runtime"]


class SceneActorFact(StrictContract):
    actor_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,159}$")
    actor_guid: str = Field(pattern=r"^[0-9a-f]{32}$")
    actor_path: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=160)
    class_path: str = Field(min_length=1, max_length=512)
    transform: TransformFact
    bounds: BoundsFact
    tags: list[str] = Field(default_factory=list, max_length=64)
    data_layers: list[str] = Field(default_factory=list, max_length=32)
    material_slots: list[MaterialSlotFact] = Field(default_factory=list, max_length=256)
    light: LightFact | None = None
    pcg_components: list[PCGComponentFact] = Field(default_factory=list, max_length=32)
    protected: bool
    editable: bool
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_actor_authority_and_children(self) -> SceneActorFact:
        if self.protected and self.editable:
            raise ValueError("protected actors cannot be marked editable")
        if len(self.tags) != len(set(self.tags)):
            raise ValueError("actor tags must be unique")
        if len(self.data_layers) != len(set(self.data_layers)):
            raise ValueError("actor data layers must be unique")
        slot_indices = [item.slot_index for item in self.material_slots]
        if len(slot_indices) != len(set(slot_indices)):
            raise ValueError("material slot indices must be unique per actor")
        component_ids = [item.component_id for item in self.pcg_components]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("PCG component IDs must be unique per actor")
        return self


class StagingCapability(StrictContract):
    strategy: Literal["data_layer", "level_instance", "candidate_level"]
    available: bool
    reason: str = Field(min_length=1, max_length=400)


class SceneDigitalTwin(StrictContract):
    schema_id: Literal["scene-digital-twin/1"] = "scene-digital-twin/1"
    twin_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    source_package_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    captured_at: datetime
    actors: list[SceneActorFact] = Field(min_length=1, max_length=100000)
    staging_capabilities: list[StagingCapability] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def validate_unique_scene_facts(self) -> SceneDigitalTwin:
        actor_ids = [item.actor_id for item in self.actors]
        if len(actor_ids) != len(set(actor_ids)):
            raise ValueError("actor IDs must be unique")
        actor_guids = [item.actor_guid for item in self.actors]
        if len(actor_guids) != len(set(actor_guids)):
            raise ValueError("actor GUIDs must be unique")
        component_ids = [
            component.component_id
            for actor in self.actors
            for component in actor.pcg_components
        ]
        if len(component_ids) != len(set(component_ids)):
            raise ValueError("PCG component IDs must be unique across the scene")
        strategies = [item.strategy for item in self.staging_capabilities]
        if len(strategies) != len(set(strategies)):
            raise ValueError("staging capability strategies must be unique")
        if not any(item.available for item in self.staging_capabilities):
            raise ValueError("at least one staging strategy must be available")
        return self

    def canonical_sha256(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class WriteScope(StrictContract):
    stage_id: str = Field(pattern=r"^artflow-[a-z0-9][a-z0-9._-]{2,119}$")
    asset_root: str = Field(pattern=ARTFLOW_ASSET_ROOT_PATTERN)
    target_actor_ids: list[str] = Field(min_length=1, max_length=128)

    @field_validator("target_actor_ids")
    @classmethod
    def unique_target_actor_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("write-scope target actor IDs must be unique")
        return value


class OperationBudget(StrictContract):
    max_actor_mutations: int = Field(ge=0, le=10000)
    max_spawned_actors: int = Field(ge=0, le=100000)
    max_duration_seconds: int = Field(ge=1, le=3600)


class OperationValidator(StrictContract):
    kind: Literal[
        "protected_fingerprint",
        "bounds",
        "no_collision",
        "actor_budget",
        "pcg_graph_allowlist",
        "light_parameter_bounds",
        "zero_source_mutations",
    ]
    required: bool = True


class SceneOperationBase(StrictContract):
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,119}$")
    depends_on: list[str] = Field(default_factory=list, max_length=64)
    expected_source_fingerprints: dict[str, str] = Field(min_length=1, max_length=128)
    write_scope: WriteScope
    idempotency_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{7,199}$")
    budget: OperationBudget
    validators: list[OperationValidator] = Field(min_length=1, max_length=16)
    cleanup: Literal["restore_staged_properties", "delete_generated_actors"]

    @field_validator("depends_on")
    @classmethod
    def unique_dependencies(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("operation dependencies must be unique")
        return value

    @field_validator("expected_source_fingerprints")
    @classmethod
    def validate_fingerprints(cls, value: dict[str, str]) -> dict[str, str]:
        for fingerprint in value.values():
            if len(fingerprint) != 64 or any(character not in "0123456789abcdef" for character in fingerprint):
                raise ValueError("source fingerprints must be lowercase SHA-256")
        return value


class SetLightingRig(SceneOperationBase):
    operation_type: Literal["set_lighting_rig"] = "set_lighting_rig"
    target_light_ids: list[str] = Field(min_length=1, max_length=32)
    intensity: float | None = Field(default=None, ge=0, le=1000000)
    color_srgb: list[float] | None = Field(default=None, min_length=3, max_length=3)
    temperature_kelvin: float | None = Field(default=None, ge=1000, le=20000)
    rotation: Rotator | None = None

    @model_validator(mode="after")
    def require_change_and_matching_scope(self) -> SetLightingRig:
        if all(
            value is None
            for value in (self.intensity, self.color_srgb, self.temperature_kelvin, self.rotation)
        ):
            raise ValueError("lighting operation must change at least one parameter")
        if set(self.target_light_ids) != set(self.write_scope.target_actor_ids):
            raise ValueError("lighting targets must exactly match the write scope")
        if self.color_srgb is not None and any(
            channel < 0 or channel > 1 for channel in self.color_srgb
        ):
            raise ValueError("lighting color channels must be between 0 and 1")
        return self


class ApplyPCGLayout(SceneOperationBase):
    operation_type: Literal["apply_pcg_layout"] = "apply_pcg_layout"
    component_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,159}$")
    approved_graph_path: str = Field(pattern=r"^/Game/ArtFlow/PCG/[A-Za-z0-9_./-]+$")
    graph_parameters: dict[str, PrimitiveParameter] = Field(min_length=1, max_length=64)
    seed: int = Field(ge=0, le=2147483647)


SceneOperation = Annotated[
    SetLightingRig | ApplyPCGLayout,
    Field(discriminator="operation_type"),
]


class SceneChangePlan(StrictContract):
    schema_id: Literal["scene-change-plan/1"] = "scene-change-plan/1"
    plan_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    twin_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    twin_sha256: str = Field(pattern=SHA256_PATTERN)
    created_at: datetime
    operations: list[SceneOperation] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def validate_operation_dag(self) -> SceneChangePlan:
        by_id = {item.operation_id: item for item in self.operations}
        if len(by_id) != len(self.operations):
            raise ValueError("operation IDs must be unique")
        for operation in self.operations:
            if operation.operation_id in operation.depends_on:
                raise ValueError("an operation cannot depend on itself")
            unknown = sorted(set(operation.depends_on) - set(by_id))
            if unknown:
                raise ValueError(f"operation depends on unknown IDs: {', '.join(unknown)}")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(operation_id: str) -> None:
            if operation_id in visiting:
                raise ValueError("operation dependency graph must be acyclic")
            if operation_id in visited:
                return
            visiting.add(operation_id)
            for dependency in by_id[operation_id].depends_on:
                visit(dependency)
            visiting.remove(operation_id)
            visited.add(operation_id)

        for operation_id in by_id:
            visit(operation_id)
        return self

    def canonical_sha256(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


class PlannedOperationSummary(StrictContract):
    operation_id: str
    operation_type: Literal["set_lighting_rig", "apply_pcg_layout"]
    target_ids: list[str] = Field(min_length=1)
    parameter_names: list[str] = Field(min_length=1)


class SceneDryRunReceipt(StrictContract):
    schema_id: Literal["scene-dry-run-receipt/1"] = "scene-dry-run-receipt/1"
    receipt_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    twin_id: str
    twin_sha256: str = Field(pattern=SHA256_PATTERN)
    plan_id: str
    plan_sha256: str = Field(pattern=SHA256_PATTERN)
    source_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_scene_fingerprint_before: str = Field(pattern=SHA256_PATTERN)
    source_scene_fingerprint_after: str = Field(pattern=SHA256_PATTERN)
    staging_strategy: Literal["data_layer", "level_instance", "candidate_level"]
    stage_id: str = Field(pattern=r"^artflow-[a-z0-9][a-z0-9._-]{2,119}$")
    planned_operations: list[PlannedOperationSummary] = Field(min_length=1)
    protected_invariants: dict[str, str] = Field(min_length=1)
    dry_run: Literal[True] = True
    committed_mutation_count: Literal[0] = 0
    created_at: datetime

    @model_validator(mode="after")
    def prove_zero_write_dry_run(self) -> SceneDryRunReceipt:
        if self.source_scene_fingerprint_before != self.source_scene_fingerprint_after:
            raise ValueError("dry-run source scene fingerprint must remain unchanged")
        return self
