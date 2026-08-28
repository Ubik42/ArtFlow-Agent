from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .scene_delta import (
    SHA256_PATTERN,
    UNREAL_OBJECT_PATH_PATTERN,
    OperationBudget,
    OperationValidator,
    PrimitiveParameter,
    Rotator,
    StrictContract,
    WriteScope,
)

SceneDomain = Literal["material", "pcg", "lighting", "asset"]


class PlanBudget(StrictContract):
    max_operations: int = Field(ge=1, le=64)
    max_total_actor_mutations: int = Field(ge=0, le=10000)
    max_total_spawned_actors: int = Field(ge=0, le=100000)
    max_total_duration_seconds: int = Field(ge=1, le=7200)
    max_parallel_preparations: int = Field(ge=1, le=8)


class MultiDomainOperationBase(StrictContract):
    operation_id: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,119}$")
    domain: SceneDomain
    depends_on: list[str] = Field(default_factory=list, max_length=64)
    expected_source_fingerprints: dict[str, str] = Field(min_length=1, max_length=128)
    write_scope: WriteScope
    idempotency_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{7,199}$")
    budget: OperationBudget
    validators: list[OperationValidator] = Field(min_length=1, max_length=16)
    uncertainty: float = Field(ge=0, le=1)
    uncertainty_reason: str = Field(min_length=1, max_length=400)
    minimal_change_rank: int = Field(ge=0, le=3)
    capability_preferences: list[str] = Field(min_length=1, max_length=8)
    compensation: Literal[
        "restore_staged_properties",
        "delete_generated_actors",
        "delete_generated_assets",
    ]

    @field_validator("depends_on", "capability_preferences")
    @classmethod
    def unique_lists(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("dependencies and capability preferences must be unique")
        return value

    @field_validator("expected_source_fingerprints")
    @classmethod
    def validate_fingerprints(cls, value: dict[str, str]) -> dict[str, str]:
        if any(len(item) != 64 or any(char not in "0123456789abcdef" for char in item) for item in value.values()):
            raise ValueError("source fingerprints must be lowercase SHA-256")
        return value

    @model_validator(mode="after")
    def require_target_preconditions(self) -> MultiDomainOperationBase:
        missing = set(self.write_scope.target_actor_ids) - set(self.expected_source_fingerprints)
        if missing:
            raise ValueError("every write target must have an expected source fingerprint")
        return self


class BindPBRMaterial(MultiDomainOperationBase):
    operation_type: Literal["bind_pbr_material"] = "bind_pbr_material"
    domain: Literal["material"] = "material"
    target_actor_id: str = Field(min_length=3, max_length=160)
    material_instance_path: str = Field(pattern=UNREAL_OBJECT_PATH_PATTERN)
    texture_set_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    slot_index: int = Field(ge=0, le=255)

    @model_validator(mode="after")
    def validate_material_scope(self) -> BindPBRMaterial:
        if self.write_scope.target_actor_ids != [self.target_actor_id]:
            raise ValueError("material target must exactly match write scope")
        if not self.material_instance_path.startswith(self.write_scope.asset_root + "/"):
            raise ValueError("material instance must be inside the operation asset root")
        return self


class ConfigureReviewedPCG(MultiDomainOperationBase):
    operation_type: Literal["configure_reviewed_pcg"] = "configure_reviewed_pcg"
    domain: Literal["pcg"] = "pcg"
    target_actor_id: str = Field(min_length=3, max_length=160)
    component_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]{2,159}$")
    reviewed_graph_path: str = Field(pattern=r"^/Game/ArtFlow/PCG/[A-Za-z0-9_./-]+$")
    reviewed_graph_sha256: str = Field(pattern=SHA256_PATTERN)
    graph_parameters: dict[str, PrimitiveParameter] = Field(min_length=1, max_length=64)
    seed: int = Field(ge=0, le=2147483647)

    @model_validator(mode="after")
    def validate_pcg_scope(self) -> ConfigureReviewedPCG:
        if self.write_scope.target_actor_ids != [self.target_actor_id]:
            raise ValueError("PCG target must exactly match write scope")
        return self


class PatchLightingRig(MultiDomainOperationBase):
    operation_type: Literal["patch_lighting_rig"] = "patch_lighting_rig"
    domain: Literal["lighting"] = "lighting"
    target_light_ids: list[str] = Field(min_length=1, max_length=32)
    intensity: float | None = Field(default=None, ge=0, le=1000000)
    temperature_kelvin: float | None = Field(default=None, ge=1000, le=20000)
    rotation: Rotator | None = None

    @model_validator(mode="after")
    def validate_lighting_scope(self) -> PatchLightingRig:
        if set(self.target_light_ids) != set(self.write_scope.target_actor_ids):
            raise ValueError("lighting targets must exactly match write scope")
        if self.intensity is None and self.temperature_kelvin is None and self.rotation is None:
            raise ValueError("lighting patch must change at least one property")
        return self


class ReuseProjectAssets(MultiDomainOperationBase):
    operation_type: Literal["reuse_project_assets"] = "reuse_project_assets"
    domain: Literal["asset"] = "asset"
    target_actor_id: str = Field(min_length=3, max_length=160)
    asset_paths: list[str] = Field(min_length=1, max_length=64)
    spawn_count: int = Field(ge=1, le=10000)
    license_policy: Literal["project_owned", "redistributable"]

    @field_validator("asset_paths")
    @classmethod
    def validate_project_assets(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("project asset paths must be unique")
        if any(not path.startswith("/Game/ArtFlow/") for path in value):
            raise ValueError("asset reuse is limited to the ArtFlow project namespace")
        return value

    @model_validator(mode="after")
    def validate_asset_scope_and_budget(self) -> ReuseProjectAssets:
        if self.write_scope.target_actor_ids != [self.target_actor_id]:
            raise ValueError("asset target must exactly match write scope")
        if self.spawn_count > self.budget.max_spawned_actors:
            raise ValueError("asset spawn count exceeds the operation budget")
        return self


MultiDomainOperation = Annotated[
    BindPBRMaterial | ConfigureReviewedPCG | PatchLightingRig | ReuseProjectAssets,
    Field(discriminator="operation_type"),
]


class MultiDomainSceneDeltaPlan(StrictContract):
    schema_id: Literal["scene-delta-plan/2"] = "scene-delta-plan/2"
    plan_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    twin_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    twin_sha256: str = Field(pattern=SHA256_PATTERN)
    visual_intent: str = Field(min_length=8, max_length=2000)
    minimal_change_policy: Literal[
        "parameters_then_project_assets_then_generated_assets"
    ] = "parameters_then_project_assets_then_generated_assets"
    protected_actor_ids: list[str] = Field(min_length=1, max_length=1024)
    budget: PlanBudget
    created_at: datetime
    operations: list[MultiDomainOperation] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_plan(self) -> MultiDomainSceneDeltaPlan:
        if len(self.operations) > self.budget.max_operations:
            raise ValueError("operation count exceeds the plan budget")
        by_id = {item.operation_id: item for item in self.operations}
        if len(by_id) != len(self.operations):
            raise ValueError("operation IDs must be unique")
        protected = set(self.protected_actor_ids)
        if any(protected.intersection(item.write_scope.target_actor_ids) for item in self.operations):
            raise ValueError("protected actors cannot appear in an operation write scope")
        stage_ids = {item.write_scope.stage_id for item in self.operations}
        asset_roots = {item.write_scope.asset_root for item in self.operations}
        if len(stage_ids) != 1 or len(asset_roots) != 1:
            raise ValueError("all operations must share one staging identity and asset root")
        if sum(item.budget.max_actor_mutations for item in self.operations) > self.budget.max_total_actor_mutations:
            raise ValueError("actor mutation budget overflow")
        if sum(item.budget.max_spawned_actors for item in self.operations) > self.budget.max_total_spawned_actors:
            raise ValueError("spawned actor budget overflow")
        if sum(item.budget.max_duration_seconds for item in self.operations) > self.budget.max_total_duration_seconds:
            raise ValueError("duration budget overflow")
        for operation in self.operations:
            unknown = sorted(set(operation.depends_on) - set(by_id))
            if unknown:
                raise ValueError(f"operation depends on unknown IDs: {', '.join(unknown)}")
            if operation.operation_id in operation.depends_on:
                raise ValueError("an operation cannot depend on itself")

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
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
