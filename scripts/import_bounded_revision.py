from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
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
    parser = argparse.ArgumentParser()
    parser.add_argument("raw_output", type=Path)
    args = parser.parse_args()
    request = BoundedRevisionRequest.model_validate_json(
        (OUTPUT_ROOT / "revision-request.json").read_text(encoding="utf-8")
    )
    adoption = CandidateAdoptionDecision.model_validate_json(
        (OUTPUT_ROOT / "adoption-decision.json").read_text(encoding="utf-8")
    )
    parent = RUN_ROOT / ".agent-artifacts" / "provider-outputs" / (
        f"{adoption.artifact_sha256}.png"
    )
    store = AgentEventStore(RUN_ROOT / "agent-events.sqlite3")
    state = store.load(RUN_ID)
    if state.bounded_revision_result is not None:
        existing = state.bounded_revision_result
        raw_sha256 = hashlib.sha256(args.raw_output.read_bytes()).hexdigest()
        if existing.receipt.raw_artifact_sha256 != raw_sha256:
            raise RuntimeError("A different raw output cannot replace the recorded revision")
        (OUTPUT_ROOT / "bounded-revision-result.json").write_text(
            json.dumps(existing.model_dump(mode="json"), indent=2) + "\n",
            encoding="utf-8",
        )
        print(
            f"EVENTS={state.last_sequence} REVISION={existing.revision_id} "
            f"COMPOSITE={existing.composite_artifact_sha256} "
            f"OUTSIDE_CHANGED={existing.leakage.outside_changed_pixels} "
            f"INSIDE_CHANGED={existing.leakage.inside_changed_pixels} REUSED=true"
        )
        return
    result = import_and_composite_revision(
        request,
        args.raw_output.resolve(),
        parent,
        OUTPUT_ROOT,
        imported_at=datetime.now(UTC),
    )
    persisted = store.record_bounded_revision_result(RUN_ID, result)
    (OUTPUT_ROOT / "bounded-revision-result.json").write_text(
        json.dumps(result.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"EVENTS={persisted.last_sequence} REVISION={result.revision_id} "
        f"COMPOSITE={result.composite_artifact_sha256} "
        f"OUTSIDE_CHANGED={result.leakage.outside_changed_pixels} "
        f"INSIDE_CHANGED={result.leakage.inside_changed_pixels}"
    )


if __name__ == "__main__":
    main()
