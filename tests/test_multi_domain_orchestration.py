from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.contracts import MultiDomainSceneDeltaPlan
from artflow_agent.scene_orchestration import CapabilityAttestation, compile_multi_domain_dry_run

ROOT = Path(__file__).resolve().parents[1]


def payload() -> dict[str, object]:
    return json.loads((ROOT / "examples" / "m9-ruin-altar-scene-delta-plan.json").read_text(encoding="utf-8"))


def capabilities() -> list[CapabilityAttestation]:
    values = json.loads((ROOT / "examples" / "m9-capability-attestations.json").read_text(encoding="utf-8"))
    return [CapabilityAttestation.model_validate(item) for item in values]


def observed(plan: MultiDomainSceneDeltaPlan) -> dict[str, str]:
    return {
        target_id: fingerprint
        for operation in plan.operations
        for target_id, fingerprint in operation.expected_source_fingerprints.items()
    }


def test_four_domain_plan_routes_fallback_and_serializes_unreal_apply() -> None:
    plan = MultiDomainSceneDeltaPlan.model_validate(payload())
    receipt = compile_multi_domain_dry_run(plan, capabilities(), observed(plan))

    assert {item.domain for item in plan.operations} == {"material", "pcg", "lighting", "asset"}
    assert receipt.preparation_waves == [
        ["asset-reuse", "lighting-patch", "material-bind"],
        ["pcg-layout"],
    ]
    assert receipt.unreal_apply_order == [
        "asset-reuse",
        "lighting-patch",
        "material-bind",
        "pcg-layout",
    ]
    asset_route = next(item for item in receipt.routes if item.operation_id == "asset-reuse")
    assert asset_route.capability_id == "asset.catalog.reuse.v1"
    assert receipt.failed_domain_reopen["material"] == ["material-bind"]
    assert receipt.committed_mutation_count == 0


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("script", "Extra inputs are not permitted"),
        ("protected", "protected actors cannot appear"),
        ("cycle", "must be acyclic"),
        ("budget", "spawned actor budget overflow"),
    ],
)
def test_plan_rejects_hostile_or_unbounded_changes(mutation: str, message: str) -> None:
    value = payload()
    operations = value["operations"]
    if mutation == "script":
        operations[0]["python"] = "unreal.SystemLibrary.execute_console_command(...)"
    elif mutation == "protected":
        operations[0]["write_scope"]["target_actor_ids"] = ["protected-blockout"]
        operations[0]["target_actor_id"] = "protected-blockout"
        operations[0]["expected_source_fingerprints"] = {"protected-blockout": "a" * 64}
    elif mutation == "cycle":
        operations[0]["depends_on"] = ["pcg-layout"]
    else:
        value["budget"]["max_total_spawned_actors"] = 5
    with pytest.raises(ValidationError, match=message):
        MultiDomainSceneDeltaPlan.model_validate(value)


def test_router_rejects_stale_fingerprint_and_unreviewed_graph() -> None:
    plan = MultiDomainSceneDeltaPlan.model_validate(payload())
    stale = observed(plan)
    stale["key-light"] = "f" * 64
    with pytest.raises(ValueError, match="stale source fingerprint"):
        compile_multi_domain_dry_run(plan, capabilities(), stale)

    attestations = capabilities()
    pcg = next(item for item in attestations if item.domain == "pcg")
    broken = pcg.model_copy(update={"reviewed_resource_ids": []})
    attestations[attestations.index(pcg)] = broken
    with pytest.raises(ValueError, match="not attested for the reviewed resource"):
        compile_multi_domain_dry_run(plan, attestations, observed(plan))


def test_contract_rejects_generated_asset_path_outside_project_namespace() -> None:
    value = deepcopy(payload())
    value["operations"][1]["asset_paths"] = ["/Engine/EditorMeshes/Bad"]
    with pytest.raises(ValidationError, match="limited to the ArtFlow project namespace"):
        MultiDomainSceneDeltaPlan.model_validate(value)
