from __future__ import annotations

import argparse
import os
from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore, AgentRuntimeError
from artflow_agent.multimodal_critic import (
    EvaluatorDisagreement,
    MultimodalCriticObservation,
    MultimodalTribunalReport,
    multimodal_report_id,
)
from artflow_agent.tribunal import (
    TribunalArtifact,
    evaluate_negative_control,
    report_fingerprint,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bind a bounded multimodal critic observation to the real tribunal."
    )
    parser.add_argument("root", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--observation", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    store = AgentEventStore(root / "agent-events.sqlite3")
    state = store.load(args.run_id)
    if state.multimodal_tribunal is not None:
        print(state.multimodal_tribunal.model_dump_json(indent=2))
        return 0
    if state.tribunal_report is None or not state.negative_controls:
        raise AgentRuntimeError("Multimodal tribunal prerequisites are missing")
    observation = MultimodalCriticObservation.model_validate_json(
        args.observation.read_text(encoding="utf-8")
    )
    negative = state.negative_controls[-1]
    artifact_root = root / ".agent-artifacts" / "provider-outputs"
    evidence = TribunalArtifact(
        role="negative_control",
        artifact_sha256=negative.receipt.artifact.sha256,
        receipt_binding_sha256=negative.receipt.request_binding_sha256,
        width=negative.receipt.width,
        height=negative.receipt.height,
    )
    deterministic = evaluate_negative_control(
        state.tribunal_report.dossier,
        evidence,
        root / "beauty.png",
        artifact_root / f"{negative.receipt.artifact.sha256}.png",
    )
    base_sha256 = report_fingerprint(state.tribunal_report)
    report = MultimodalTribunalReport(
        report_id=multimodal_report_id(
            {
                "base": base_sha256,
                "negative": negative.receipt.request_binding_sha256,
                "critic": observation.fingerprint(),
            }
        ),
        base_tribunal_sha256=base_sha256,
        negative_control=negative,
        deterministic_negative_result=deterministic,
        critic=observation,
        disagreements=[
            EvaluatorDisagreement(
                candidate_role="negative_control",
                subject="aesthetic appeal versus production eligibility",
                deterministic_verdict="fail",
                critic_verdict="pass",
                resolution="hard_gate_precedence",
            )
        ],
    )
    store.record_multimodal_tribunal(args.run_id, report)
    output = root.parent / "m4-s2-negative-control" / "multimodal-tribunal-report.json"
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
