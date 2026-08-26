from __future__ import annotations

import json
from pathlib import Path

from artflow_agent.adoption import CandidateAdoptionDecision
from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.bounded_revision import (
    BoundedRevisionRequest,
    import_and_composite_revision,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_ROOT = ROOT / "artifacts" / "goal" / "m3-s11-local-run"
OUTPUT_ROOT = ROOT / "artifacts" / "goal" / "m4-s3-bounded-revision"
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def main() -> None:
    store = AgentEventStore(RUN_ROOT / "agent-events.sqlite3")
    state = store.load(RUN_ID)
    existing = state.bounded_revision_result
    if existing is None:
        raise RuntimeError("The first bounded revision attempt is missing")
    if existing.compositor_id == "feathered-inside-mask-v2":
        print(
            f"EVENTS={state.last_sequence} REVISION={existing.revision_id} "
            f"ATTEMPT={existing.attempt} COMPOSITE={existing.composite_artifact_sha256} "
            "REUSED=true"
        )
        return
    request = BoundedRevisionRequest.model_validate_json(
        (OUTPUT_ROOT / "revision-request.json").read_text(encoding="utf-8")
    )
    adoption = CandidateAdoptionDecision.model_validate_json(
        (OUTPUT_ROOT / "adoption-decision.json").read_text(encoding="utf-8")
    )
    parent = RUN_ROOT / ".agent-artifacts" / "provider-outputs" / (
        f"{adoption.artifact_sha256}.png"
    )
    raw = OUTPUT_ROOT / existing.receipt.raw_artifact_path
    corrected = import_and_composite_revision(
        request,
        raw,
        parent,
        OUTPUT_ROOT,
        imported_at=existing.receipt.imported_at,
        compositor_id="feathered-inside-mask-v2",
        attempt=existing.attempt + 1,
    )
    persisted = store.record_bounded_revision_correction(RUN_ID, corrected)
    (OUTPUT_ROOT / "bounded-revision-result.json").write_text(
        json.dumps(corrected.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"EVENTS={persisted.last_sequence} REVISION={corrected.revision_id} "
        f"ATTEMPT={corrected.attempt} COMPOSITE={corrected.composite_artifact_sha256} "
        f"OUTSIDE_CHANGED={corrected.leakage.outside_changed_pixels}"
    )


if __name__ == "__main__":
    main()
