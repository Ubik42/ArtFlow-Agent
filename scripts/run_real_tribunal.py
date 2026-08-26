from __future__ import annotations

import argparse
import os
from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore, AgentRuntimeError
from artflow_agent.tribunal import (
    EvaluationDossier,
    TribunalArtifact,
    dossier_id_for,
    evaluate_dossier,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the persisted real matched candidates")
    parser.add_argument("root", type=Path)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    store = AgentEventStore(root / "agent-events.sqlite3")
    state = store.load(args.run_id)
    if state.tribunal_report is not None:
        print(state.tribunal_report.model_dump_json(indent=2))
        return 0
    if state.scene is None or len(state.provider_executions) != 1:
        raise AgentRuntimeError("Real tribunal requires the matched M3 run")
    local = state.provider_executions[0]
    codex = state.codex_image_candidates[-1]
    if local.receipt is None:
        raise AgentRuntimeError("Local receipt is missing")
    beauty = next(item for item in state.scene.package.passes if item.kind == "beauty")
    local_artifact = local.receipt.artifacts[0]
    artifact_root = root / ".agent-artifacts" / "provider-outputs"
    paths = {
        "source": root / "beauty.png",
        "local_comfy": artifact_root / f"{local_artifact.sha256}.png",
        "codex_image": artifact_root / f"{codex.receipt.artifact.sha256}.png",
    }
    payload = {
        "scene_package_id": state.scene.package.package_id,
        "scene_package_sha256": state.scene.archive_sha256,
        "beauty_sha256": beauty.artifact.sha256,
        "local_sha256": local_artifact.sha256,
        "local_binding_sha256": local.route_fingerprint,
        "codex_sha256": codex.receipt.artifact.sha256,
        "codex_binding_sha256": codex.receipt.request_binding_sha256,
    }
    dossier = EvaluationDossier(
        dossier_id=dossier_id_for(payload),
        scene_package_id=state.scene.package.package_id,
        scene_package_sha256=state.scene.archive_sha256,
        beauty_sha256=beauty.artifact.sha256,
        preserve=state.scene.package.art_intent.preserve,
        prohibit=state.scene.package.art_intent.prohibit,
        artifacts=[
            TribunalArtifact(
                role="source",
                artifact_sha256=beauty.artifact.sha256,
                receipt_binding_sha256=state.scene.archive_sha256,
                width=state.scene.package.camera.width,
                height=state.scene.package.camera.height,
            ),
            TribunalArtifact(
                role="local_comfy",
                artifact_sha256=local_artifact.sha256,
                receipt_binding_sha256=local.route_fingerprint,
                width=1024,
                height=576,
            ),
            TribunalArtifact(
                role="codex_image",
                artifact_sha256=codex.receipt.artifact.sha256,
                receipt_binding_sha256=codex.receipt.request_binding_sha256,
                width=codex.receipt.width,
                height=codex.receipt.height,
            ),
        ],
    )
    report = evaluate_dossier(dossier, paths)
    store.record_tribunal_report(args.run_id, report)
    output = root.parent / "m4-s1-tribunal" / "tribunal-report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".json.tmp")
    temporary.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, output)
    print(report.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
