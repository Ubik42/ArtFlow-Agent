from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.scene_session import SceneDomainCorrectionPlan
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
    content_root = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
    )
    content_root.mkdir(parents=True)
    source_file = content_root / "ArtFlowDemo.umap"
    source_file.write_bytes(b"source-level")
    source_sha = hashlib.sha256(source_file.read_bytes()).hexdigest()
    candidate_file = content_root / f"{plan['candidate_destination'].removeprefix('/Game/')}.umap"
    candidate_file.parent.mkdir(parents=True)
    candidate_file.write_bytes(b"candidate-level")
    candidate_sha = hashlib.sha256(candidate_file.read_bytes()).hexdigest()
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
        "candidate_level_sha256": candidate_sha,
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
    assert work["definition"]["source_level_sha256"] == intake["evaluation_input"][
        "source_level_sha256"
    ]
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
    assert plan["lighting_intensity"] == 3.2
    assert plan["lighting_temperature_kelvin"] == 7200.0

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


def test_failed_correction_can_be_requeued_with_the_same_content_identity(
    tmp_path: Path,
) -> None:
    client, database, _ = _succeeded_work(tmp_path)
    candidate_base = f"/api/agent/runs/{RUN_ID}/scene-candidate-work"
    intake = client.post(f"{candidate_base}/evaluate").json()[
        "scene_candidate_intake"
    ]
    client.post(
        f"{candidate_base}/visual-observation",
        json=_lighting_failure_observation(intake),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-correction-work"
    first = client.post(f"{base}/queue").json()["scene_correction_work"]
    definition = first["definition"]
    claim = {
        "schema_id": "artflow-scene-correction-claim/1",
        "work_sha256": definition["work_sha256"],
        "session_sha256": definition["session_sha256"],
        "worker_id": "ue-editor-correction",
    }
    assert client.post(f"{base}/claim", json=claim).status_code == 200
    assert client.post(
        f"{base}/progress",
        json={
            "schema_id": "artflow-scene-correction-progress/1",
            "work_sha256": definition["work_sha256"],
            "worker_id": "ue-editor-correction",
            "status": "failed",
            "action_id": "m20-correction-failed-once",
            "message": "宿主在写入前安全退出",
        },
    ).status_code == 200

    retried = client.post(f"{base}/queue")
    assert retried.status_code == 200
    retried_work = retried.json()["scene_correction_work"]
    assert retried_work["status"] == "queued"
    assert retried_work["definition"] == definition
    reclaimed = client.post(f"{base}/claim", json=claim)
    assert reclaimed.status_code == 200
    assert reclaimed.json()["scene_correction_work"]["status"] == "claimed"
    events = AgentEventStore(database).events(RUN_ID)
    assert [event.event_type for event in events].count(
        "scene_correction_work_queued"
    ) == 2


def _succeeded_correction(
    tmp_path: Path,
) -> tuple[TestClient, Path, dict[str, object]]:
    client, database, _ = _succeeded_work(tmp_path)
    candidate_base = f"/api/agent/runs/{RUN_ID}/scene-candidate-work"
    intake = client.post(f"{candidate_base}/evaluate").json()[
        "scene_candidate_intake"
    ]
    client.post(
        f"{candidate_base}/visual-observation",
        json=_lighting_failure_observation(intake),
    )
    base = f"/api/agent/runs/{RUN_ID}/scene-correction-work"
    projection = client.post(f"{base}/queue").json()
    work = projection["scene_correction_work"]
    definition = work["definition"]
    project_root = tmp_path / "project"
    candidate_file = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / f"{definition['candidate_scene'].removeprefix('/Game/')}.umap"
    )
    candidate_file.write_bytes(b"corrected-candidate-level")
    candidate_sha = hashlib.sha256(candidate_file.read_bytes()).hexdigest()
    output = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Saved/ArtFlowSceneBridge/SceneCorrections"
        / definition["work_id"]
    )
    output.mkdir(parents=True)
    beauty = output / "corrected-beauty.png"
    Image.new("RGB", (640, 360), (72, 98, 146)).save(beauty)
    beauty_sha = hashlib.sha256(beauty.read_bytes()).hexdigest()
    receipt = {
        "schema_id": "artflow-session-lighting-correction-receipt/1",
        "work_id": definition["work_id"],
        "work_sha256": definition["work_sha256"],
        "evaluation_sha256": definition["evaluation_sha256"],
        "correction_sha256": definition["correction_plan"]["correction_sha256"],
        "candidate_plan_sha256": definition["candidate_plan_sha256"],
        "candidate_scene": definition["candidate_scene"],
        "source_level_sha256_before": definition["source_level_sha256"],
        "source_level_sha256_after": definition["source_level_sha256"],
        "source_level_unchanged": True,
        "protected_state_before": "6" * 64,
        "protected_state_after": "6" * 64,
        "generated_instance_count_before": 12,
        "generated_instance_count_after": 12,
        "intensity_before": 5.5,
        "intensity_after": 3.2,
        "temperature_before": 4200.0,
        "temperature_after": 7200.0,
        "candidate_level_sha256": candidate_sha,
        "corrected_beauty_path": str(beauty),
        "corrected_beauty_sha256": beauty_sha,
        "reconciled": False,
        "completed_at": "2026-08-30T13:00:00Z",
    }
    receipt_path = output / "lighting-correction-receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    outcome = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    claim = {
        "schema_id": "artflow-scene-correction-claim/1",
        "work_sha256": definition["work_sha256"],
        "session_sha256": definition["session_sha256"],
        "worker_id": "ue-editor-correction",
    }
    assert client.post(f"{base}/claim", json=claim).status_code == 200
    for status in ("executing", "reconciling"):
        assert client.post(
            f"{base}/progress",
            json={
                "schema_id": "artflow-scene-correction-progress/1",
                "work_sha256": definition["work_sha256"],
                "worker_id": "ue-editor-correction",
                "status": status,
                "action_id": f"m20-correction-real-{status}",
            },
        ).status_code == 200
    assert client.post(
        f"{base}/progress",
        json={
            "schema_id": "artflow-scene-correction-progress/1",
            "work_sha256": definition["work_sha256"],
            "worker_id": "ue-editor-correction",
            "status": "succeeded",
            "action_id": "m20-correction-real-succeeded",
            "outcome_sha256": outcome,
        },
    ).status_code == 200
    return client, database, projection


def test_corrected_candidate_is_reevaluated_and_adopted_from_current_evidence(
    tmp_path: Path,
) -> None:
    client, database, before = _succeeded_correction(tmp_path)
    base = f"/api/agent/runs/{RUN_ID}/scene-correction-work"
    first = client.post(f"{base}/evaluate")
    replay = client.post(f"{base}/evaluate")
    assert first.status_code == replay.status_code == 200
    intake = first.json()["scene_correction_intake"]
    assert intake == replay.json()["scene_correction_intake"]
    assert intake["technical_evaluation"]["status"] == "eligible_for_visual_review"
    assert len(intake["technical_evaluation"]["checks"]) == 7
    assert intake["evaluation_input"]["corrected_beauty_sha256"] != before[
        "scene_candidate_intake"
    ]["evaluation_input"]["candidate_beauty_sha256"]
    served = client.get(f"{base}/beauty")
    assert served.status_code == 200
    assert hashlib.sha256(served.content).hexdigest() == intake["evaluation_input"][
        "corrected_beauty_sha256"
    ]

    observation = seal_visual_observation(
        {
            "input_sha256": intake["evaluation_input"]["input_sha256"],
            "source_beauty_sha256": intake["evaluation_input"][
                "source_beauty_sha256"
            ],
            "candidate_beauty_sha256": intake["evaluation_input"][
                "corrected_beauty_sha256"
            ],
            "claims": [
                {
                    "dimension": "camera_composition",
                    "verdict": "passed",
                    "confidence": 0.99,
                    "rationale": "纠正回渲继续保持源场景的相机、画幅和主体占位。",
                },
                {
                    "dimension": "protected_structure",
                    "verdict": "passed",
                    "confidence": 0.99,
                    "rationale": "受保护灰盒轮廓与原候选保持一致，没有发生结构改写。",
                },
                {
                    "dimension": "spatial_readability",
                    "verdict": "passed",
                    "confidence": 0.95,
                    "rationale": "十二个 PCG 实例仍维持清晰的前景与中景空间节奏。",
                },
                {
                    "dimension": "lighting_direction",
                    "verdict": "passed",
                    "confidence": 0.86,
                    "rationale": "降低强度并提升色温后，画面形成更冷静的清晨光照方向。",
                },
                {
                    "dimension": "visual_coherence",
                    "verdict": "passed",
                    "confidence": 0.84,
                    "rationale": "冷色主光与灰盒、墙体及空间层次保持统一，没有引入冲突。",
                },
            ],
            "recommended_failed_domains": [],
        }
    ).model_dump(mode="json")
    evaluated = client.post(f"{base}/visual-observation", json=observation)
    replayed = client.post(f"{base}/visual-observation", json=observation)
    assert evaluated.status_code == replayed.status_code == 200
    payload = evaluated.json()
    corrected = payload["scene_correction_visual_verdict"]["domain_evaluation"]
    assert corrected["status"] == "accepted"
    assert corrected["failed_domains"] == []
    failed_findings = {
        item["domain"]: item
        for item in payload["scene_candidate_visual_verdict"]["domain_evaluation"][
            "findings"
        ]
    }
    corrected_findings = {item["domain"]: item for item in corrected["findings"]}
    assert corrected_findings["image"] == failed_findings["image"]
    assert corrected_findings["pcg"] == failed_findings["pcg"]
    assert payload["scene_candidate_evaluation"]["corrected_evaluation"] == corrected

    adopted = client.post(f"{base}/adopt")
    adopted_replay = client.post(f"{base}/adopt")
    assert adopted.status_code == adopted_replay.status_code == 200
    decision = adopted.json()["scene_candidate_adoption"]["decision"]
    assert decision["orchestrator"] == "codex"
    assert decision["evaluation_sha256"] == corrected["evaluation_sha256"]
    assert adopted.json()["scene_variant_lineage"] is None
    assert len(AgentEventStore(database).events(RUN_ID)) == 19


def test_failed_corrected_rerender_queues_complete_registered_light_rig(
    tmp_path: Path,
) -> None:
    client, _, _ = _succeeded_correction(tmp_path)
    base = f"/api/agent/runs/{RUN_ID}/scene-correction-work"
    intake = client.post(f"{base}/evaluate").json()["scene_correction_intake"]
    input_record = intake["evaluation_input"]
    observation = seal_visual_observation(
        {
            "input_sha256": input_record["input_sha256"],
            "source_beauty_sha256": input_record["source_beauty_sha256"],
            "candidate_beauty_sha256": input_record["corrected_beauty_sha256"],
            "claims": [
                {
                    "dimension": "camera_composition",
                    "verdict": "passed",
                    "confidence": 0.99,
                    "rationale": "相机、画幅和主体占位保持不变。",
                },
                {
                    "dimension": "protected_structure",
                    "verdict": "passed",
                    "confidence": 0.99,
                    "rationale": "受保护结构没有被灯光修改。",
                },
                {
                    "dimension": "spatial_readability",
                    "verdict": "passed",
                    "confidence": 0.95,
                    "rationale": "PCG 空间节奏继续保持清晰。",
                },
                {
                    "dimension": "lighting_direction",
                    "verdict": "failed",
                    "confidence": 0.93,
                    "rationale": "第二盏定向光仍使画面保持硬质中性日照。",
                },
                {
                    "dimension": "visual_coherence",
                    "verdict": "passed",
                    "confidence": 0.88,
                    "rationale": "场景布局与光照修改没有产生结构冲突。",
                },
            ],
            "recommended_failed_domains": ["lighting"],
        }
    ).model_dump(mode="json")
    failed = client.post(f"{base}/visual-observation", json=observation).json()
    previous = failed["scene_correction_work"]
    previous_verdict = failed["scene_correction_visual_verdict"]["domain_evaluation"]

    queued = client.post(f"{base}/queue")
    assert queued.status_code == 200
    projection = queued.json()
    work = projection["scene_correction_work"]
    definition = work["definition"]
    plan = definition["correction_plan"]
    assert definition["parent_work_sha256"] == previous["definition"]["work_sha256"]
    assert definition["parent_outcome_sha256"] == previous["outcome_sha256"]
    assert definition["evaluation_sha256"] == previous_verdict["evaluation_sha256"]
    assert plan["lighting_intensity"] == 2.2
    assert plan["lighting_temperature_kelvin"] == 8500.0
    assert plan["key_light_pitch_degrees"] == -18.0
    assert plan["key_light_yaw_degrees"] == -45.0
    assert plan["secondary_light_intensity"] == 0.25
    assert plan["secondary_light_temperature_kelvin"] == 9000.0
    assert projection["scene_correction_intake"] is None
    assert projection["scene_correction_visual_verdict"] is None

    invalid_payload = {**plan, "secondary_light_temperature_kelvin": None}
    invalid_payload.pop("schema_id")
    invalid_payload.pop("correction_id")
    invalid_payload.pop("correction_sha256")
    invalid_sha = hashlib.sha256(
        json.dumps(
            {key: value for key, value in invalid_payload.items() if value is not None},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    try:
        SceneDomainCorrectionPlan(
            correction_id=f"domain-correction-{invalid_sha[:12]}",
            correction_sha256=invalid_sha,
            **invalid_payload,
        )
    except ValueError as exc:
        assert "complete rig" in str(exc)
    else:
        raise AssertionError("partial registered light rig must be rejected")
