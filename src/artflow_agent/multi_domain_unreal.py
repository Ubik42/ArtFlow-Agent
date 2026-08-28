from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from artflow_agent.contracts.scene_delta import (
    SHA256_PATTERN,
    UNREAL_OBJECT_PATH_PATTERN,
    BoundsFact,
    StrictContract,
)


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class BoundSceneActor(StrictContract):
    role: Literal["editable", "protected", "key_light", "authored_camera"]
    actor_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    label: str = Field(min_length=1, max_length=160)
    source_fingerprint: str = Field(pattern=SHA256_PATTERN)


class MaterialExecutionBinding(StrictContract):
    target_role: Literal["editable"] = "editable"
    slot_index: int = Field(ge=0, le=255)
    material_instance_path: str = Field(pattern=UNREAL_OBJECT_PATH_PATTERN)
    pbr_request_sha256: str = Field(pattern=SHA256_PATTERN)
    pbr_receipt_sha256: str = Field(pattern=SHA256_PATTERN)


class AssetExecutionBinding(StrictContract):
    asset_paths: list[str] = Field(min_length=1, max_length=64)
    license_policy: Literal["project_owned", "redistributable"]

    @field_validator("asset_paths")
    @classmethod
    def project_namespace_only(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("asset paths must be unique")
        if any(not path.startswith("/Game/ArtFlow/") for path in value):
            raise ValueError("multi-domain execution only accepts ArtFlow project assets")
        return value


class LightingExecutionBinding(StrictContract):
    target_role: Literal["key_light"] = "key_light"
    intensity: float = Field(ge=0, le=1000000)
    temperature_kelvin: float = Field(ge=1000, le=20000)


class PCGExecutionBinding(StrictContract):
    target_role: Literal["editable"] = "editable"
    component_id: str = Field(pattern=r"^[0-9a-f]{32}:pcg_[a-z0-9_]+$")
    reviewed_graph_path: str = Field(pattern=r"^/Game/ArtFlow/PCG/[A-Za-z0-9_./-]+$")
    reviewed_graph_sha256: str = Field(pattern=SHA256_PATTERN)
    seed: int = Field(ge=0, le=2147483647)
    expected_instance_count: int = Field(ge=1, le=10000)
    exclusion_bounds: BoundsFact


class MultiViewRenderBinding(StrictContract):
    authored_camera_role: Literal["authored_camera"] = "authored_camera"
    validation_camera_location: list[float] = Field(min_length=3, max_length=3)
    validation_camera_target: list[float] = Field(min_length=3, max_length=3)
    width: int = Field(ge=64, le=4096)
    height: int = Field(ge=64, le=4096)


class MultiDomainUnrealRequest(StrictContract):
    schema_id: Literal["multi-domain-unreal-request/1"] = "multi-domain-unreal-request/1"
    request_id: str = Field(pattern=r"^m9-ue-[0-9a-f]{24}$")
    plan_id: str
    plan_sha256: str = Field(pattern=SHA256_PATTERN)
    dry_run_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    twin_id: str
    twin_sha256: str = Field(pattern=SHA256_PATTERN)
    source_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_scene_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_scene_path: str = Field(pattern=r"^/Game/ArtFlow/Staging/[A-Za-z0-9_.-]+$")
    stage_id: str = Field(pattern=r"^artflow-[a-z0-9][a-z0-9._-]{2,119}$")
    actors: list[BoundSceneActor] = Field(min_length=4, max_length=4)
    operation_order: list[Literal["asset-reuse", "lighting-patch", "material-bind", "pcg-layout"]] = Field(min_length=4, max_length=4)
    material: MaterialExecutionBinding
    asset: AssetExecutionBinding
    lighting: LightingExecutionBinding
    pcg: PCGExecutionBinding
    render: MultiViewRenderBinding
    expected_protected_state_sha256: str = Field(pattern=SHA256_PATTERN)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_bound_request(self) -> MultiDomainUnrealRequest:
        roles = [item.role for item in self.actors]
        if sorted(roles) != ["authored_camera", "editable", "key_light", "protected"]:
            raise ValueError("request must bind exactly four required actor roles")
        if self.operation_order != ["asset-reuse", "lighting-patch", "material-bind", "pcg-layout"]:
            raise ValueError("Unreal operation order must match the reviewed M9-S1 dry run")
        unsigned = self.model_dump(mode="json", exclude={"request_sha256"})
        if canonical_sha256(unsigned) != self.request_sha256:
            raise ValueError("multi-domain request fingerprint mismatch")
        return self


class MultiDomainOperationResult(StrictContract):
    operation_id: Literal["asset-reuse", "lighting-patch", "material-bind", "pcg-layout"]
    status: Literal["executed", "reconciled"]
    evidence: dict[str, str | int | float | bool]


class MultiDomainUnrealReceipt(StrictContract):
    schema_id: Literal["multi-domain-unreal-receipt/1"] = "multi-domain-unreal-receipt/1"
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["staged", "reconciled"]
    engine_version: str
    candidate_scene_path: str
    operation_results: list[MultiDomainOperationResult] = Field(min_length=4, max_length=4)
    material_instance_path: str
    pcg_graph_path: str
    generated_instance_count: int = Field(ge=1, le=10000)
    source_scene_sha256_before: str = Field(pattern=SHA256_PATTERN)
    source_scene_sha256_after: str = Field(pattern=SHA256_PATTERN)
    protected_state_before: str = Field(pattern=SHA256_PATTERN)
    protected_state_after: str = Field(pattern=SHA256_PATTERN)
    authored_render_path: str = Field(min_length=1)
    authored_render_sha256: str = Field(pattern=SHA256_PATTERN)
    validation_render_path: str = Field(min_length=1)
    validation_render_sha256: str = Field(pattern=SHA256_PATTERN)
    completed_at: datetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_receipt(self) -> MultiDomainUnrealReceipt:
        if self.source_scene_sha256_before != self.source_scene_sha256_after:
            raise ValueError("multi-domain execution changed the source scene")
        if self.protected_state_before != self.protected_state_after:
            raise ValueError("multi-domain execution changed the protected actor")
        if [item.operation_id for item in self.operation_results] != [
            "asset-reuse", "lighting-patch", "material-bind", "pcg-layout"
        ]:
            raise ValueError("operation results are not in the reviewed serial order")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("multi-domain receipt fingerprint mismatch")
        return self


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
