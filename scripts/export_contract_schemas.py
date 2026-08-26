from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.comparison import (
    ComparisonAuthorizationDecision,
    ProviderComparisonManifest,
    ProviderComparisonPlan,
)
from artflow_agent.contracts import (
    ApprovalGrant,
    ProviderCapabilityManifest,
    ProviderExecutionReceipt,
    RouteDecision,
    SceneConstraintPackage,
)
from artflow_agent.hosted_execution import CompiledHostedRequest, HostedAuthorityPacket
from artflow_agent.live_run import LiveRunAuthorizationDossier

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = {
    "approval-grant.v1.schema.json": ApprovalGrant.model_json_schema(),
    "comparison-authorization-decision.v1.schema.json": (
        ComparisonAuthorizationDecision.model_json_schema()
    ),
    "hosted-authority-packet.v1.schema.json": HostedAuthorityPacket.model_json_schema(),
    "hosted-image-edit-request.v1.schema.json": CompiledHostedRequest.model_json_schema(),
    "live-run-authorization-dossier.v1.schema.json": (
        LiveRunAuthorizationDossier.model_json_schema()
    ),
    "provider-capability-manifest.v1.schema.json": ProviderCapabilityManifest.model_json_schema(),
    "provider-comparison-manifest.v1.schema.json": ProviderComparisonManifest.model_json_schema(),
    "provider-comparison-plan.v1.schema.json": ProviderComparisonPlan.model_json_schema(),
    "provider-execution-receipt.v1.schema.json": ProviderExecutionReceipt.model_json_schema(),
    "route-decision.v1.schema.json": RouteDecision.model_json_schema(),
    "scene-constraint-package.v1.schema.json": SceneConstraintPackage.model_json_schema(),
}


def serialized(schema: dict[str, object]) -> str:
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Export ArtFlow cross-language JSON Schemas.")
    parser.add_argument("--check", action="store_true", help="Fail if generated schemas differ.")
    args = parser.parse_args()
    stale: list[str] = []
    for name, schema in SCHEMAS.items():
        path = ROOT / "contracts" / name
        expected = serialized(schema)
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
    if stale:
        parser.error("stale generated schemas: " + ", ".join(stale))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
