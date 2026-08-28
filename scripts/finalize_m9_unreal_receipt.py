from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.multi_domain_unreal import (
    MultiDomainUnrealReceipt,
    MultiDomainUnrealRequest,
    canonical_sha256,
    file_sha256,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind M9 apply, reconcile and multi-view evidence.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--apply-result", type=Path, required=True)
    parser.add_argument("--reconcile-result", type=Path, required=True)
    parser.add_argument("--multi-view", type=Path, required=True)
    parser.add_argument("--authored-render", type=Path, required=True)
    parser.add_argument("--validation-render", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = MultiDomainUnrealRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    apply_result = json.loads(args.apply_result.read_text(encoding="utf-8"))
    reconcile = json.loads(args.reconcile_result.read_text(encoding="utf-8"))
    multi_view = json.loads(args.multi_view.read_text(encoding="utf-8"))
    for artifact in (apply_result, reconcile, multi_view):
        if artifact["request_id"] != request.request_id or artifact["request_sha256"] != request.request_sha256:
            raise SystemExit("M9 host evidence is not bound to the request")
    if reconcile["status"] != "reconciled":
        raise SystemExit("exact M9 replay did not reconcile")
    if apply_result["operation_results"] != reconcile["operation_results"]:
        raise SystemExit("M9 replay changed operation results")
    if multi_view["source_scene_sha256_before"] != multi_view["source_scene_sha256_after"]:
        raise SystemExit("multi-view capture changed the source scene")
    authored_sha = file_sha256(args.authored_render)
    validation_sha = file_sha256(args.validation_render)
    if authored_sha != multi_view["authored_render_sha256"] or validation_sha != multi_view["validation_render_sha256"]:
        raise SystemExit("copied M9 render hashes differ from the C++ capture receipt")
    facts = {
        "schema_id": "multi-domain-unreal-receipt/1",
        "request_id": request.request_id,
        "request_sha256": request.request_sha256,
        "status": reconcile["status"],
        "engine_version": reconcile["engine_version"],
        "candidate_scene_path": reconcile["candidate_scene_path"],
        "operation_results": reconcile["operation_results"],
        "material_instance_path": reconcile["material_instance_path"],
        "pcg_graph_path": reconcile["pcg_graph_path"],
        "generated_instance_count": reconcile["generated_instance_count"],
        "source_scene_sha256_before": reconcile["source_scene_sha256_before"],
        "source_scene_sha256_after": reconcile["source_scene_sha256_after"],
        "protected_state_before": reconcile["protected_state_before"],
        "protected_state_after": reconcile["protected_state_after"],
        "authored_render_path": args.authored_render.as_posix(),
        "authored_render_sha256": authored_sha,
        "validation_render_path": args.validation_render.as_posix(),
        "validation_render_sha256": validation_sha,
        "completed_at": reconcile["completed_at"],
    }
    facts["receipt_sha256"] = canonical_sha256(facts)
    receipt = MultiDomainUnrealReceipt.model_validate(facts)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(receipt.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
