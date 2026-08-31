from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.scene_disposition import (
    SessionCandidateExecutionReceipt,
    compile_adoption_decision,
    compile_publish_request,
    file_sha256,
)
from artflow_agent.scene_session import SceneCandidateDomainEvaluation, SceneCandidatePlan


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile an evidence-bound Session disposition.")
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--execution", type=Path, required=True)
    parser.add_argument("--technical", type=Path, required=True)
    parser.add_argument("--candidate-map", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--decision", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()

    evaluation = SceneCandidateDomainEvaluation.model_validate_json(
        args.evaluation.read_text(encoding="utf-8")
    )
    plan = SceneCandidatePlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    execution = SessionCandidateExecutionReceipt.model_validate_json(
        args.execution.read_text(encoding="utf-8")
    )
    technical = json.loads(args.technical.read_text(encoding="utf-8"))
    decision = compile_adoption_decision(
        evaluation=evaluation,
        plan=plan,
        execution=execution,
        execution_receipt_sha256=file_sha256(args.execution),
        candidate_file=args.candidate_map,
        source_file=args.source_map,
    )
    request = compile_publish_request(
        decision,
        protected_state_sha256=technical["checks"]["protected_state_sha256"],
        material_path=technical["material_instance_path"],
        instance_count=technical["checks"]["pcg_instance_count"],
    )
    args.decision.parent.mkdir(parents=True, exist_ok=True)
    args.request.parent.mkdir(parents=True, exist_ok=True)
    args.decision.write_text(decision.model_dump_json(indent=2) + "\n", encoding="utf-8")
    args.request.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(request.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
