from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.harness_eval import persist_or_load_harness_scorecard

ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "artifacts" / "goal" / "m5-s3-harness"
DATABASE = ROOT / "artifacts" / "goal" / "m3-s11-local-run" / "agent-events.sqlite3"
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def main() -> None:
    scorecard = persist_or_load_harness_scorecard(
        OUTPUT / "harness-scorecard.json",
        database=DATABASE,
        run_id=RUN_ID,
        recovery_scorecard_path=(
            ROOT / "artifacts" / "goal" / "m5-s1-recovery" / "recovery-scorecard.json"
        ),
        memory_scorecard_path=(
            ROOT / "artifacts" / "goal" / "m5-s2-memory" / "memory-scorecard.json"
        ),
    )
    if scorecard.passed_cases != scorecard.total_cases:
        raise SystemExit(scorecard.model_dump_json(indent=2))
    store = AgentEventStore(DATABASE)
    if store.load(RUN_ID).harness_scorecard is None:
        store.record_harness_scorecard(RUN_ID, scorecard)
    print(scorecard.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
