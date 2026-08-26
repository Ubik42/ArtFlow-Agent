from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.recovery_eval import run_frozen_recovery_matrix

ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "artifacts" / "goal" / "m5-s1-recovery"
DATABASE = ROOT / "artifacts" / "goal" / "m3-s11-local-run" / "agent-events.sqlite3"
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def main() -> None:
    scorecard = run_frozen_recovery_matrix(
        OUTPUT,
        project_root=ROOT,
        production_database=DATABASE,
        production_run_id=RUN_ID,
    )
    print(scorecard.model_dump_json(indent=2))
    if scorecard.passed_cases != scorecard.total_cases:
        raise SystemExit(1)
    store = AgentEventStore(DATABASE)
    if store.load(RUN_ID).recovery_scorecard is None:
        store.record_recovery_scorecard(RUN_ID, scorecard)


if __name__ == "__main__":
    main()
