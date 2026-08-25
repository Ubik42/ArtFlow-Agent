from datetime import UTC, datetime

import pytest

from artflow_agent.delivery import package_run
from artflow_agent.domain import ArtBrief, Candidate, GenerationReceipt
from artflow_agent.planning import DeterministicPlanner
from artflow_agent.run_store import RunStateError, RunStore


def _brief() -> ArtBrief:
    return ArtBrief(
        project_name="fixture",
        source_image="source.png",
        intent="Create a controlled environment lighting variant.",
        preserve=["composition"],
        avoid=["characters"],
        variant_count=1,
    )


def test_store_enforces_approval_and_human_selection(tmp_path) -> None:
    brief = _brief()
    store = RunStore(tmp_path)
    state = store.create(brief, DeterministicPlanner().create_plan(brief), run_id="run-1")
    assert state.status == "awaiting_approval"
    with pytest.raises(RunStateError, match="before explicit approval"):
        store.mark_running("run-1")

    store.approve("run-1")
    store.mark_running("run-1")
    now = datetime.now(UTC)
    receipt = GenerationReceipt(
        prompt_id="prompt-1",
        recipe_id="composition-preserving-v1",
        recipe_version="1.0.0",
        workflow_sha256="a" * 64,
        queued_at=now,
        completed_at=now,
    )
    receipt_path = store.save_receipt("run-1", receipt)
    candidate_path = tmp_path / "run-1" / "artifacts" / "result.png"
    candidate_path.write_bytes(b"generated-image")
    candidates = [
        Candidate(
            candidate_id="candidate-1",
            direction_name="cold-storm",
            image_path=str(candidate_path),
            receipt_path=str(receipt_path),
        )
    ]
    store.set_candidates("run-1", candidates)
    final_state = store.select("run-1", "candidate-1")
    assert final_state.status == "completed"
    assert final_state.selected_candidate_id == "candidate-1"
    assert [event.event_type for event in store.events("run-1")] == [
        "run_created",
        "plan_approved",
        "generation_started",
        "generation_receipt_saved",
        "candidates_ready",
        "candidate_selected",
    ]
    package_path = package_run(store, "run-1", tmp_path / "delivery.zip")
    assert package_path.is_file()
    assert package_path.stat().st_size > 0

    revision_brief = ArtBrief(
        project_name="fixture-revision",
        task_type="masked_refinement",
        source_image="replaced-by-selected-parent-artifact",
        intent="Refine the selected arch while preserving all unmasked pixels.",
        preserve=["outside-mask pixels"],
        variant_count=1,
    )
    revision = store.create_revision(
        "run-1",
        revision_brief,
        DeterministicPlanner().create_plan(revision_brief),
        run_id="revision-1",
    )
    assert revision.status == "awaiting_approval"
    assert revision.parent_run_id == "run-1"
    assert revision.source_candidate_id == "candidate-1"
    assert revision.brief.source_image == str(candidate_path.resolve())
    assert revision.plan.directions[0].recipe_id == "masked-refinement-v1"
