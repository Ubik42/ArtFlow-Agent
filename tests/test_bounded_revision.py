from __future__ import annotations

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageChops

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.web_api import create_app

ROOT = Path(__file__).parents[1]
RUN_ROOT = ROOT / "artifacts" / "goal" / "m3-s11-local-run"
REVISION_ROOT = ROOT / "artifacts" / "goal" / "m4-s3-bounded-revision"
DATABASE = RUN_ROOT / "agent-events.sqlite3"
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"


def test_real_revision_replays_adoption_request_failure_and_correction() -> None:
    state = AgentEventStore(DATABASE).load(RUN_ID)

    assert state.last_sequence == 25
    assert state.pending_decisions == []
    assert state.adoption_decision is not None
    assert state.adoption_decision.selected_role == "codex_image"
    assert state.bounded_revision_request is not None
    assert state.bounded_revision_result is not None
    assert [item.compositor_id for item in state.bounded_revision_attempts] == [
        "hard-mask-v1",
        "feathered-inside-mask-v2",
    ]
    assert state.bounded_revision_result.leakage.outside_changed_pixels == 0
    assert state.recovery_scorecard is not None
    assert state.recovery_scorecard.passed_cases == 6
    assert state.recovery_scorecard.duplicate_side_effect_count == 0
    assert len([record for record in state.memory_records if record.status == "active"]) == 3
    assert state.memory_scorecard is not None
    assert state.memory_scorecard.passed_cases == 6
    assert state.harness_scorecard is not None
    assert state.harness_scorecard.passed_cases == 20
    assert state.verified_delivery is not None
    assert state.verified_delivery.status == "verified_with_declared_c2pa_limitation"


def test_real_verified_delivery_visible_evidence_is_hash_bound() -> None:
    state = AgentEventStore(DATABASE).load(RUN_ID)
    assert state.verified_delivery is not None
    delivery = state.verified_delivery
    client = TestClient(create_app(runs_dir=RUN_ROOT, agent_database=DATABASE))
    base = (
        f"/api/agent/runs/{RUN_ID}/verified-deliveries/"
        f"{delivery.delivery_sha256}/visible/"
    )
    response = client.get(base + delivery.visible_evidence_sha256)
    assert response.status_code == 200
    assert response.headers["x-content-sha256"] == delivery.visible_evidence_sha256
    assert hashlib.sha256(response.content).hexdigest() == delivery.visible_evidence_sha256
    mismatch = client.get(base + ("0" * 64))
    assert mismatch.status_code == 409


def test_real_revision_pixel_guard_recomputes_exactly() -> None:
    payload = json.loads(
        (REVISION_ROOT / "bounded-revision-result.json").read_text(encoding="utf-8")
    )
    request = json.loads(
        (REVISION_ROOT / "revision-request.json").read_text(encoding="utf-8")
    )
    parent = Image.open(
        RUN_ROOT
        / ".agent-artifacts"
        / "provider-outputs"
        / f"{payload['leakage']['parent_sha256']}.png"
    ).convert("RGB")
    composite = Image.open(
        REVISION_ROOT / payload["composite_artifact_path"]
    ).convert("RGB")
    mask = Image.open(REVISION_ROOT / request["mask"]["artifact_path"]).convert("L")
    difference = ImageChops.difference(parent, composite)

    outside_changed = inside_changed = 0
    for changed, allowed in zip(
        difference.get_flattened_data(), mask.get_flattened_data(), strict=True
    ):
        if changed != (0, 0, 0):
            if allowed:
                inside_changed += 1
            else:
                outside_changed += 1
    assert outside_changed == payload["leakage"]["outside_changed_pixels"] == 0
    assert inside_changed == payload["leakage"]["inside_changed_pixels"] == 42803


def test_revision_artifacts_are_served_only_by_persisted_identity(tmp_path: Path) -> None:
    state = AgentEventStore(DATABASE).load(RUN_ID)
    request = state.bounded_revision_request
    result = state.bounded_revision_result
    assert request is not None and result is not None
    client = TestClient(create_app(runs_dir=tmp_path, agent_database=DATABASE))
    base = f"/api/agent/runs/{RUN_ID}/bounded-revisions/{result.revision_id}/artifacts"

    response = client.get(f"{base}/composite/{result.composite_artifact_sha256}")
    assert response.status_code == 200
    assert response.headers["x-content-sha256"] == result.composite_artifact_sha256
    assert response.content == (
        REVISION_ROOT / result.composite_artifact_path
    ).read_bytes()
    assert client.get(f"{base}/mask/{'0' * 64}").status_code == 409
