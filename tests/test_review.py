from PIL import Image

from artflow_agent.domain import ArtBrief, Candidate
from artflow_agent.planning import DeterministicPlanner
from artflow_agent.review import create_contact_sheet, evaluate_trajectory
from artflow_agent.run_store import RunStore


def test_contact_sheet_and_trajectory_evaluation(tmp_path) -> None:
    image_path = tmp_path / "candidate.png"
    Image.new("RGB", (64, 32), "#4f86c6").save(image_path)
    candidate = Candidate(
        candidate_id="c1",
        direction_name="cold-storm",
        image_path=str(image_path),
        receipt_path="receipts/prompt-1.json",
    )
    sheet_path = create_contact_sheet([candidate], tmp_path / "sheet.jpg", cell_size=(100, 80))
    assert sheet_path.exists()
    assert Image.open(sheet_path).size == (300, 124)

    brief = ArtBrief(
        project_name="fixture",
        source_image="source.png",
        intent="Create one controlled lighting direction.",
        preserve=["composition"],
        avoid=["characters"],
        variant_count=1,
    )
    store = RunStore(tmp_path / "runs")
    state = store.create(brief, DeterministicPlanner().create_plan(brief), run_id="run")
    store.approve("run")
    state = store.mark_running("run")
    state.candidates = [candidate]
    state.selected_candidate_id = "c1"
    state.status = "completed"
    evaluation = evaluate_trajectory(
        state,
        ["run_created", "plan_approved", "generation_started"],
        receipt_count=1,
    )
    assert evaluation.passed is True
