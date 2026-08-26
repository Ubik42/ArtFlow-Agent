from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.memory_eval import run_frozen_memory_suite
from artflow_agent.production_memory import build_memory_proposal

ROOT = Path(__file__).parents[1]
OUTPUT = ROOT / "artifacts" / "goal" / "m5-s2-memory"
DATABASE = ROOT / "artifacts" / "goal" / "m3-s11-local-run" / "agent-events.sqlite3"
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def main() -> None:
    scorecard = run_frozen_memory_suite(
        OUTPUT, source_database=DATABASE, run_id=RUN_ID
    )
    if scorecard.passed_cases != scorecard.total_cases:
        raise SystemExit(scorecard.model_dump_json(indent=2))
    store = AgentEventStore(DATABASE)
    state = store.load(RUN_ID)
    if state.scene is None:
        raise SystemExit("Real run has no scene")
    project_id = state.scene.package.package_id
    hashes = {event.event_type: event.event_hash for event in store.events(RUN_ID)}
    seeds = [
        build_memory_proposal(
            memory_id="memory-recovery-exactly-once-v1",
            kind="episodic",
            project_id=project_id,
            subject_key="run.recovery.exactly_once",
            value="六项冻结恢复案例全部通过；未知完成状态禁止自动重提。",
            tags=["recovery", "exactly-once"],
            version=1,
            source_run_id=RUN_ID,
            source_event_hashes=[hashes["recovery_scorecard_recorded"]],
        ),
        build_memory_proposal(
            memory_id="memory-camera-preservation-v1",
            kind="semantic",
            project_id=project_id,
            subject_key="scene.camera.preserve",
            value="保持已验证的 16:9 机位、构图与受保护主体剪影。",
            tags=["camera", "constraint", "unreal"],
            version=1,
            source_run_id=RUN_ID,
            source_event_hashes=[hashes["scene_attached"]],
        ),
        build_memory_proposal(
            memory_id="memory-revision-no-regen-v1",
            kind="procedural",
            project_id=project_id,
            subject_key="revision.correct_without_regeneration",
            value="局部修订出现合成接缝时，保留失败尝试并复用原始生成制品，在遮罩内纠正。",
            tags=["revision", "recovery", "mask"],
            version=1,
            source_run_id=RUN_ID,
            source_event_hashes=[
                hashes["bounded_revision_recorded"],
                hashes["bounded_revision_corrected"],
            ],
        ),
    ]
    for proposal in seeds:
        store.propose_memory(RUN_ID, proposal)
        store.resolve_memory(RUN_ID, proposal.memory_id)
    if store.load(RUN_ID).memory_scorecard is None:
        store.record_memory_scorecard(RUN_ID, scorecard)
    print(scorecard.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
