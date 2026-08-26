from pathlib import Path

from artflow_agent.recovery_eval import FROZEN_CASES, run_frozen_recovery_matrix


def test_frozen_recovery_matrix_proves_exactly_once_boundaries(tmp_path) -> None:
    root = Path(__file__).parents[1]
    scorecard = run_frozen_recovery_matrix(
        tmp_path / "recovery",
        project_root=root,
        production_database=(
            root / "artifacts" / "goal" / "m3-s11-local-run" / "agent-events.sqlite3"
        ),
        production_run_id=(
            "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"
        ),
    )

    assert scorecard.total_cases == len(FROZEN_CASES) == 6
    assert scorecard.passed_cases == scorecard.total_cases
    assert scorecard.duplicate_side_effect_count == 0
    assert all(case.provider_side_effect_count == 1 for case in scorecard.cases)
    assert next(
        case for case in scorecard.cases if case.case_id == "completion_unknown"
    ).terminal_event_count == 0
    adoption = next(
        case for case in scorecard.cases if case.case_id == "adoption_revision_replay"
    )
    assert adoption.adoption_side_effect_count == 1
    assert adoption.revision_side_effect_count == 1
