import json
import sqlite3
from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.harness_contracts import HarnessScorecard
from artflow_agent.harness_eval import run_harness_suite

ROOT = Path(__file__).parents[1]
DATABASE = ROOT / "artifacts" / "goal" / "m3-s11-local-run" / "agent-events.sqlite3"
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def _scorecard(database: Path = DATABASE):
    persisted = ROOT / "artifacts" / "goal" / "m5-s3-harness" / "harness-scorecard.json"
    if persisted.exists():
        return HarnessScorecard.model_validate_json(persisted.read_bytes())
    return run_harness_suite(
        database=database,
        run_id=RUN_ID,
        recovery_scorecard_path=(
            ROOT / "artifacts" / "goal" / "m5-s1-recovery" / "recovery-scorecard.json"
        ),
        memory_scorecard_path=(
            ROOT / "artifacts" / "goal" / "m5-s2-memory" / "memory-scorecard.json"
        ),
    )


def test_harness_suite_aggregates_named_denominators_and_provenance() -> None:
    scorecard = _scorecard()
    by_metric = {metric.metric_id: metric for metric in scorecard.metrics}

    assert scorecard.passed_cases == scorecard.total_cases == 20
    assert {case.domain for case in scorecard.cases} == {
        "context", "capability", "routing", "policy", "recovery", "memory"
    }
    assert all(case.citations for case in scorecard.cases)
    assert by_metric["context_case_recall"].denominator == 3
    assert by_metric["route_policy_accuracy"].denominator == 5
    assert by_metric["false_interrupt_rate"].value == 0
    assert by_metric["duplicate_side_effect_rate"].value == 0
    assert by_metric["fixture_external_cost"].value == 0
    assert scorecard.scorecard_sha256 == scorecard.expected_sha256()


def test_harness_scorecard_event_is_content_addressed_and_idempotent(tmp_path) -> None:
    database = tmp_path / "events.sqlite3"
    with sqlite3.connect(DATABASE) as source, sqlite3.connect(database) as target:
        source.backup(target)
    scorecard = _scorecard(database)
    store = AgentEventStore(database)
    before = len(store.events(RUN_ID))
    first = store.record_harness_scorecard(RUN_ID, scorecard)
    replay = store.record_harness_scorecard(RUN_ID, scorecard)

    assert first.harness_scorecard == replay.harness_scorecard == scorecard
    expected_increment = 0 if AgentEventStore(DATABASE).load(RUN_ID).harness_scorecard else 1
    assert len(store.events(RUN_ID)) == before + expected_increment
    encoded = json.dumps(scorecard.model_dump(mode="json")).casefold()
    assert "prompt" not in encoded
    assert "reasoning" not in encoded
