from __future__ import annotations

import json
from pathlib import Path

from artflow_agent.adoption import select_production_candidate
from artflow_agent.agent_runtime import AgentEventStore

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "artifacts" / "goal" / "m3-s11-local-run"
OUTPUT = ROOT / "artifacts" / "goal" / "m4-s3-bounded-revision" / "adoption-decision.json"
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def main() -> None:
    store = AgentEventStore(RUN_ROOT / "agent-events.sqlite3")
    state = store.load(RUN_ID)
    if state.tribunal_report is None or state.multimodal_tribunal is None:
        raise RuntimeError("Persisted tribunal evidence is incomplete")
    if not state.codex_image_candidates:
        raise RuntimeError("Codex production candidate is missing")
    local = state.provider_executions[0].receipt
    if local is None or not local.artifacts:
        raise RuntimeError("Local production candidate is missing")
    decision = select_production_candidate(
        state.tribunal_report,
        state.multimodal_tribunal,
        local_candidate_id=f"local-comfy:{local.artifacts[0].sha256[:20]}",
        codex_candidate_id=state.codex_image_candidates[-1].receipt.candidate_id,
    )
    persisted = store.record_candidate_adoption(RUN_ID, decision)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(decision.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"EVENTS={persisted.last_sequence} DECISION={decision.decision_id} "
        f"ROLE={decision.selected_role} ARTIFACT={decision.artifact_sha256}"
    )


if __name__ == "__main__":
    main()
