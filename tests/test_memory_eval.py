from pathlib import Path

from artflow_agent.memory_eval import run_frozen_memory_suite


def test_frozen_memory_suite_reports_exact_denominators_and_citations(tmp_path) -> None:
    root = Path(__file__).parents[1]
    scorecard = run_frozen_memory_suite(
        tmp_path / "memory-suite",
        source_database=(
            root / "artifacts" / "goal" / "m3-s11-local-run" / "agent-events.sqlite3"
        ),
        run_id="local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb",
    )

    assert scorecard.passed_cases == scorecard.total_cases == 6
    assert scorecard.retrieval_precision == 1
    assert scorecard.conflict_rejection_rate == 1
    assert {case.case_id for case in scorecard.cases} == {
        "activation_restart_replay",
        "conflict_rejection",
        "stale_version_rejection",
        "private_promotion_rejection",
        "forged_source_rejection",
        "irrelevant_retrieval_filter",
    }
