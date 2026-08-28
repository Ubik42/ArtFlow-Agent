from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from artflow_agent.contracts.multi_domain_delta import (
    MultiDomainSceneDeltaPlan,
    SceneDomain,
)
from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract


class CapabilityAttestation(StrictContract):
    capability_id: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,119}$")
    domain: SceneDomain
    tool_name: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,119}$")
    status: Literal["available", "unavailable"]
    interface_sha256: str = Field(pattern=SHA256_PATTERN)
    reviewed_resource_ids: list[str] = Field(default_factory=list, max_length=128)
    optional: bool = False
    execution_lane: Literal["parallel_prepare", "unreal_serial"]


class OperationRoute(StrictContract):
    operation_id: str
    domain: SceneDomain
    capability_id: str
    tool_name: str
    execution_lane: Literal["parallel_prepare", "unreal_serial"]


class MultiDomainDryRunReceipt(StrictContract):
    schema_id: Literal["multi-domain-dry-run-receipt/1"] = "multi-domain-dry-run-receipt/1"
    plan_id: str
    plan_sha256: str = Field(pattern=SHA256_PATTERN)
    stage_id: str
    routes: list[OperationRoute] = Field(min_length=1)
    preparation_waves: list[list[str]] = Field(min_length=1)
    unreal_apply_order: list[str] = Field(min_length=1)
    failed_domain_reopen: dict[SceneDomain, list[str]]
    committed_mutation_count: Literal[0] = 0
    source_scene_unchanged: Literal[True] = True
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_complete_schedule(self) -> MultiDomainDryRunReceipt:
        operation_ids = [item.operation_id for item in self.routes]
        if set(operation_ids) != set(self.unreal_apply_order):
            raise ValueError("route and Unreal apply operation sets must match")
        prepared = [item for wave in self.preparation_waves for item in wave]
        if set(prepared) != set(operation_ids) or len(prepared) != len(operation_ids):
            raise ValueError("preparation waves must contain every operation exactly once")
        return self


def _topological_waves(plan: MultiDomainSceneDeltaPlan) -> list[list[str]]:
    remaining = {item.operation_id: set(item.depends_on) for item in plan.operations}
    waves: list[list[str]] = []
    completed: set[str] = set()
    while remaining:
        ready = sorted(
            operation_id
            for operation_id, dependencies in remaining.items()
            if dependencies <= completed
        )
        if not ready:
            raise ValueError("validated plan unexpectedly has no schedulable operation")
        for offset in range(0, len(ready), plan.budget.max_parallel_preparations):
            waves.append(ready[offset : offset + plan.budget.max_parallel_preparations])
        completed.update(ready)
        for operation_id in ready:
            remaining.pop(operation_id)
    return waves


def compile_multi_domain_dry_run(
    plan: MultiDomainSceneDeltaPlan,
    capabilities: list[CapabilityAttestation],
    observed_source_fingerprints: dict[str, str],
) -> MultiDomainDryRunReceipt:
    by_id = {item.capability_id: item for item in capabilities}
    if len(by_id) != len(capabilities):
        raise ValueError("capability attestation IDs must be unique")
    routes: list[OperationRoute] = []
    for operation in plan.operations:
        for target_id, expected in operation.expected_source_fingerprints.items():
            if observed_source_fingerprints.get(target_id) != expected:
                raise ValueError(f"stale source fingerprint for {target_id}")
        selected = next(
            (
                by_id[capability_id]
                for capability_id in operation.capability_preferences
                if capability_id in by_id
                and by_id[capability_id].status == "available"
                and by_id[capability_id].domain == operation.domain
            ),
            None,
        )
        if selected is None:
            raise ValueError(f"no attested capability can execute {operation.operation_id}")
        reviewed_id = None
        if operation.operation_type == "configure_reviewed_pcg":
            reviewed_id = operation.reviewed_graph_sha256
        elif operation.operation_type == "bind_pbr_material":
            reviewed_id = operation.texture_set_receipt_sha256
        if reviewed_id and reviewed_id not in selected.reviewed_resource_ids:
            raise ValueError(f"capability is not attested for the reviewed resource of {operation.operation_id}")
        routes.append(
            OperationRoute(
                operation_id=operation.operation_id,
                domain=operation.domain,
                capability_id=selected.capability_id,
                tool_name=selected.tool_name,
                execution_lane=selected.execution_lane,
            )
        )

    waves = _topological_waves(plan)
    apply_order = [operation_id for wave in waves for operation_id in wave]
    reopen = {
        domain: [item.operation_id for item in plan.operations if item.domain == domain]
        for domain in ("material", "pcg", "lighting", "asset")
    }
    facts = {
        "schema_id": "multi-domain-dry-run-receipt/1",
        "plan_id": plan.plan_id,
        "plan_sha256": plan.canonical_sha256(),
        "stage_id": plan.operations[0].write_scope.stage_id,
        "routes": [item.model_dump(mode="json") for item in routes],
        "preparation_waves": waves,
        "unreal_apply_order": apply_order,
        "failed_domain_reopen": reopen,
        "committed_mutation_count": 0,
        "source_scene_unchanged": True,
    }
    facts["receipt_sha256"] = hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return MultiDomainDryRunReceipt.model_validate(facts)
