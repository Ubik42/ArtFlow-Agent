from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path

from pydantic import ValidationError

from artflow_agent.contracts import MultiDomainSceneDeltaPlan
from artflow_agent.scene_orchestration import (
    CapabilityAttestation,
    MultiDomainDryRunReceipt,
    compile_multi_domain_dry_run,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently verify the frozen M9-S1 dry run.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--capabilities", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan_payload = json.loads(args.plan.read_text(encoding="utf-8"))
    plan = MultiDomainSceneDeltaPlan.model_validate(plan_payload)
    attestations = [
        CapabilityAttestation.model_validate(item)
        for item in json.loads(args.capabilities.read_text(encoding="utf-8"))
    ]
    observed = {
        target_id: fingerprint
        for operation in plan.operations
        for target_id, fingerprint in operation.expected_source_fingerprints.items()
    }
    expected = compile_multi_domain_dry_run(plan, attestations, observed)
    persisted = MultiDomainDryRunReceipt.model_validate_json(args.receipt.read_text(encoding="utf-8"))
    if expected != persisted:
        raise SystemExit("persisted dry-run receipt does not replay from its bound inputs")

    negative_controls: dict[str, bool] = {}

    def plan_rejected(name: str, value: dict[str, object]) -> None:
        try:
            MultiDomainSceneDeltaPlan.model_validate(value)
        except ValidationError:
            negative_controls[name] = True
        else:
            raise SystemExit(f"negative control was accepted: {name}")

    injected = deepcopy(plan_payload)
    injected["operations"][0]["python"] = "run arbitrary host code"
    plan_rejected("arbitrary_code_field", injected)
    protected = deepcopy(plan_payload)
    protected["operations"][0]["target_actor_id"] = "protected-blockout"
    protected["operations"][0]["write_scope"]["target_actor_ids"] = ["protected-blockout"]
    protected["operations"][0]["expected_source_fingerprints"] = {"protected-blockout": "a" * 64}
    plan_rejected("protected_actor_target", protected)
    cycle = deepcopy(plan_payload)
    cycle["operations"][0]["depends_on"] = ["pcg-layout"]
    plan_rejected("dependency_cycle", cycle)
    overflow = deepcopy(plan_payload)
    overflow["budget"]["max_total_spawned_actors"] = 1
    plan_rejected("budget_overflow", overflow)

    stale = dict(observed)
    stale["key-light"] = "f" * 64
    try:
        compile_multi_domain_dry_run(plan, attestations, stale)
    except ValueError:
        negative_controls["stale_fingerprint"] = True
    else:
        raise SystemExit("negative control was accepted: stale_fingerprint")
    pcg_index = next(index for index, item in enumerate(attestations) if item.domain == "pcg")
    unreviewed = list(attestations)
    unreviewed[pcg_index] = unreviewed[pcg_index].model_copy(update={"reviewed_resource_ids": []})
    try:
        compile_multi_domain_dry_run(plan, unreviewed, observed)
    except ValueError:
        negative_controls["unreviewed_pcg_graph"] = True
    else:
        raise SystemExit("negative control was accepted: unreviewed_pcg_graph")

    report = {
        "schema_id": "m9-s1-independent-verification/1",
        "status": "verified",
        "plan_sha256": plan.canonical_sha256(),
        "receipt_sha256": persisted.receipt_sha256,
        "domains": sorted({item.domain for item in plan.operations}),
        "parallel_preparation_waves": persisted.preparation_waves,
        "serialized_unreal_apply_order": persisted.unreal_apply_order,
        "selected_asset_fallback": next(
            item.capability_id for item in persisted.routes if item.domain == "asset"
        ),
        "failed_domain_reopen": persisted.failed_domain_reopen,
        "negative_controls": negative_controls,
        "negative_controls_passed": sum(negative_controls.values()),
        "negative_controls_total": 6,
        "committed_mutation_count": persisted.committed_mutation_count,
    }
    report["verification_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
