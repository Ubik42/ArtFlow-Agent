from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.current_visual_critic import seal_visual_observation
from artflow_agent.web_api import create_app

RUN_ID = "unreal-artflow-ue-c4f262344b71ecfb5bf65580af4f5a1f-207d24a911c3"


def _database(tmp_path: Path) -> Path:
    root = Path(__file__).parents[1]
    source = root / "artifacts" / "goal" / "m12-s2-live-candidate-v2" / "agent-events.sqlite3"
    target = tmp_path / "agent-events.sqlite3"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def _succeeded_work(
    tmp_path: Path, *, generated_instance_count: int = 12
) -> tuple[TestClient, Path, dict[str, object]]:
    database = _database(tmp_path)
    project_root = tmp_path / "project"
    client = TestClient(
        create_app(
            runs_dir=tmp_path / "runs",
            agent_database=database,
            project_root=project_root,
        ),
        client=("127.0.0.1", 51234),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-candidate-work"
    work = client.post(f"{base}/queue").json()["scene_candidate_work"]
    definition = work["definition"]
    plan = definition["candidate_plan"]
    output = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Saved/ArtFlowSceneBridge/SceneCandidates"
        / plan["plan_id"]
    )
    output.mkdir(parents=True)
    beauty = output / "candidate-beauty.png"
    Image.new("RGB", (640, 360), (88, 112, 132)).save(beauty)
    beauty_sha = hashlib.sha256(beauty.read_bytes()).hexdigest()
    source_sha = "4" * 64
    receipt = {
        "schema_id": "artflow-session-candidate-execution-receipt/1",
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "stage_request_sha256": definition["stage_request"]["request_sha256"],
        "source_scene": plan["source_scene"],
        "source_level_sha256_before": source_sha,
        "source_level_sha256_after": source_sha,
        "source_level_unchanged": True,
        "candidate_scene": plan["candidate_destination"],
        "candidate_level_sha256": "5" * 64,
        "generated_instance_count": generated_instance_count,
        "reconciled": False,
        "candidate_beauty_path": str(beauty),
        "candidate_beauty_sha256": beauty_sha,
        "completed_at": "2026-08-30T12:00:00Z",
    }
    receipt_path = output / "candidate-execution-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    outcome = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    claim = {
        "schema_id": "artflow-scene-candidate-claim/1",
        "work_sha256": definition["work_sha256"],
        "session_sha256": definition["session_sha256"],
        "worker_id": "ue-editor-m20",
    }
    assert client.post(f"{base}/claim", json=claim).status_code == 200
    for status in ("executing", "reconciling"):
        assert client.post(
            f"{base}/progress",
            json={
                "schema_id": "artflow-scene-candidate-progress/1",
                "work_sha256": definition["work_sha256"],
                "worker_id": "ue-editor-m20",
                "status": status,
                "action_id": f"m20-{status}",
            },
        ).status_code == 200
    assert client.post(
        f"{base}/progress",
        json={
            "schema_id": "artflow-scene-candidate-progress/1",
            "work_sha256": definition["work_sha256"],
            "worker_id": "ue-editor-m20",
            "status": "succeeded",
            "action_id": "m20-succeeded",
            "outcome_sha256": outcome,
        },
    ).status_code == 200
    return client, database, work


def test_current_candidate_intake_is_content_bound_idempotent_and_replayable(
    tmp_path: Path,
) -> None:
    client, database, work = _succeeded_work(tmp_path)
    endpoint = f"/api/agent/runs/{RUN_ID}/scene-candidate-work/evaluate"

    first = client.post(endpoint)
    replay = client.post(endpoint)
    assert first.status_code == replay.status_code == 200
    intake = first.json()["scene_candidate_intake"]
    assert intake == replay.json()["scene_candidate_intake"]
    assert intake["technical_evaluation"]["status"] == "eligible_for_visual_review"
    assert intake["technical_evaluation"]["failed_domains"] == []
    assert len(intake["technical_evaluation"]["checks"]) == 6
    assert intake["evaluation_input"]["work_sha256"] == work["definition"]["work_sha256"]
    assert len(AgentEventStore(database).events(RUN_ID)) == 9

    restored = AgentEventStore(database).load(RUN_ID).scene_candidate_intake
    assert restored is not None
    assert restored == AgentEventStore(database).load(RUN_ID).scene_candidate_intake
    assert restored.technical_evaluation.status == "eligible_for_visual_review"


def test_current_candidate_intake_rejects_failed_pcg_budget_without_visual_override(
    tmp_path: Path,
) -> None:
    client, _, _ = _succeeded_work(tmp_path, generated_instance_count=999)
    response = client.post(
        f"/api/agent/runs/{RUN_ID}/scene-candidate-work/evaluate"
    )
    assert response.status_code == 200
    evaluation = response.json()["scene_candidate_intake"]["technical_evaluation"]
    assert evaluation["status"] == "rejected"
    assert evaluation["failed_domains"] == ["pcg"]
    budget = next(check for check in evaluation["checks"] if check["check_id"] == "instance_budget")
    assert budget["status"] == "failed"


def _lighting_failure_observation(intake: dict[str, object]) -> dict[str, object]:
    evaluation_input = intake["evaluation_input"]
    assert isinstance(evaluation_input, dict)
    observation = seal_visual_observation(
        {
            "input_sha256": evaluation_input["input_sha256"],
            "source_beauty_sha256": evaluation_input["source_beauty_sha256"],
            "candidate_beauty_sha256": evaluation_input["candidate_beauty_sha256"],
            "claims": [
                {
                    "dimension": "camera_composition",
                    "verdict": "passed",
                    "confidence": 0.99,
                    "rationale": "源图与候选保持相同机位、画幅和主体占位。",
                },
                {
                    "dimension": "protected_structure",
                    "verdict": "passed",
                    "confidence": 0.98,
                    "rationale": "灰盒立方体、球体与右侧墙体轮廓保持一致。",
                },
                {
                    "dimension": "spatial_readability",
                    "verdict": "passed",
                    "confidence": 0.94,
                    "rationale": "新增锥体形成可读的前中景分布且没有遮挡主体。",
                },
                {
                    "dimension": "lighting_direction",
                    "verdict": "failed",
                    "confidence": 0.96,
                    "rationale": "画面仍接近默认日照，未形成雨后清晨的冷湿空气与层次。",
                },
                {
                    "dimension": "visual_coherence",
                    "verdict": "passed",
                    "confidence": 0.9,
                    "rationale": "新增空间元素与原灰盒尺度关系一致，整体没有视觉冲突。",
                },
            ],
            "recommended_failed_domains": ["lighting"],
        }
    )
    return observation.model_dump(mode="json")


def test_current_visual_observation_produces_only_lighting_failure_and_replays(
    tmp_path: Path,
) -> None:
    client, database, _ = _succeeded_work(tmp_path)
    base = f"/api/agent/runs/{RUN_ID}/scene-candidate-work"
    intake_response = client.post(f"{base}/evaluate")
    assert intake_response.status_code == 200
    payload = _lighting_failure_observation(
        intake_response.json()["scene_candidate_intake"]
    )

    first = client.post(f"{base}/visual-observation", json=payload)
    replay = client.post(f"{base}/visual-observation", json=payload)
    assert first.status_code == replay.status_code == 200
    verdict = first.json()["scene_candidate_visual_verdict"]
    assert verdict == replay.json()["scene_candidate_visual_verdict"]
    assert verdict["domain_evaluation"]["status"] == "correction_required"
    assert verdict["domain_evaluation"]["failed_domains"] == ["lighting"]
    candidate_beauty = client.get(f"{base}/beauty")
    assert candidate_beauty.status_code == 200
    assert hashlib.sha256(candidate_beauty.content).hexdigest() == verdict[
        "visual_observation"
    ]["candidate_beauty_sha256"]
    assert len(AgentEventStore(database).events(RUN_ID)) == 10
    restored = AgentEventStore(database).load(RUN_ID).scene_candidate_visual_verdict
    assert restored is not None
    assert restored.domain_evaluation.failed_domains == ["lighting"]


def test_visual_observation_cannot_override_rejected_technical_intake(
    tmp_path: Path,
) -> None:
    client, _, _ = _succeeded_work(tmp_path, generated_instance_count=999)
    base = f"/api/agent/runs/{RUN_ID}/scene-candidate-work"
    intake_response = client.post(f"{base}/evaluate")
    payload = _lighting_failure_observation(
        intake_response.json()["scene_candidate_intake"]
    )
    response = client.post(f"{base}/visual-observation", json=payload)
    assert response.status_code == 409
    assert "rejected technical intake" in response.json()["detail"]


def test_lighting_only_correction_work_preserves_passed_evidence_and_replays(
    tmp_path: Path,
) -> None:
    client, database, _ = _succeeded_work(tmp_path)
    candidate_base = f"/api/agent/runs/{RUN_ID}/scene-candidate-work"
    intake = client.post(f"{candidate_base}/evaluate").json()[
        "scene_candidate_intake"
    ]
    observation = _lighting_failure_observation(intake)
    verdict_response = client.post(
        f"{candidate_base}/visual-observation", json=observation
    )
    assert verdict_response.status_code == 200
    verdict = verdict_response.json()["scene_candidate_visual_verdict"]

    base = f"/api/agent/runs/{RUN_ID}/scene-correction-work"
    queued = client.post(f"{base}/queue")
    replay = client.post(f"{base}/queue")
    assert queued.status_code == replay.status_code == 200
    work = queued.json()["scene_correction_work"]
    assert work == replay.json()["scene_correction_work"]
    plan = work["definition"]["correction_plan"]
    assert plan["failed_domains"] == plan["rerun_domains"] == ["lighting"]
    assert set(plan["preserved_evidence_sha256s"]) == {"image", "pcg"}
    findings = {
        item["domain"]: item["evidence_sha256"]
        for item in verdict["domain_evaluation"]["findings"]
    }
    assert plan["preserved_evidence_sha256s"] == {
        "image": findings["image"],
        "pcg": findings["pcg"],
    }
    assert plan["lighting_intensity"] == 5.5
    assert plan["lighting_temperature_kelvin"] == 4200.0

    definition = work["definition"]
    claim = {
        "schema_id": "artflow-scene-correction-claim/1",
        "work_sha256": definition["work_sha256"],
        "session_sha256": definition["session_sha256"],
        "worker_id": "ue-editor-correction",
    }
    assert client.post(f"{base}/claim", json=claim).status_code == 200
    assert client.post(
        f"{base}/claim", json={**claim, "worker_id": "ue-editor-other"}
    ).status_code == 409
    for status in ("executing", "reconciling"):
        assert client.post(
            f"{base}/progress",
            json={
                "schema_id": "artflow-scene-correction-progress/1",
                "work_sha256": definition["work_sha256"],
                "worker_id": "ue-editor-correction",
                "status": status,
                "action_id": f"m20-correction-{status}",
            },
        ).status_code == 200
    succeeded = client.post(
        f"{base}/progress",
        json={
            "schema_id": "artflow-scene-correction-progress/1",
            "work_sha256": definition["work_sha256"],
            "worker_id": "ue-editor-correction",
            "status": "succeeded",
            "action_id": "m20-correction-succeeded",
            "outcome_sha256": "8" * 64,
        },
    )
    assert succeeded.status_code == 200
    restored = AgentEventStore(database).load(RUN_ID).scene_correction_work
    assert restored is not None
    assert restored.status == "succeeded"
    assert restored.outcome_sha256 == "8" * 64
