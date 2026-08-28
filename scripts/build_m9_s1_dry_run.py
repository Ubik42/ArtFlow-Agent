from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.contracts import MultiDomainSceneDeltaPlan
from artflow_agent.scene_orchestration import CapabilityAttestation, compile_multi_domain_dry_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile the frozen M9 multi-domain dry run.")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--capabilities", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = MultiDomainSceneDeltaPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    capabilities = [
        CapabilityAttestation.model_validate(item)
        for item in json.loads(args.capabilities.read_text(encoding="utf-8"))
    ]
    observed = {
        target_id: fingerprint
        for operation in plan.operations
        for target_id, fingerprint in operation.expected_source_fingerprints.items()
    }
    receipt = compile_multi_domain_dry_run(plan, capabilities, observed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(receipt.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
