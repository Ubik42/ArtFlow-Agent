import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from artflow_agent.agent_runtime import AgentBudget, AgentEventStore, AgentRuntimeError
from artflow_agent.comparison import (
    ComparisonAuthorizationDecision,
    ComparisonChildPlan,
    ComparisonChildResult,
    ComparisonOperatorPreview,
    ProviderComparisonManifest,
    ProviderComparisonPlan,
)
from artflow_agent.scene_packages import ScenePackageArchive


def _archive(tmp_path: Path) -> Path:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "examples" / "scene-constraint-package.example.json").read_text(
            encoding="utf-8"
        )
    )
    artifacts = {
        "passes/beauty.png": b"beauty",
        "passes/depth.exr": b"depth",
        "passes/world-normal.exr": b"world-normal",
        "passes/object-id.png": b"object-id",
    }
    for item in manifest["passes"]:
        item["artifact"]["sha256"] = hashlib.sha256(
            artifacts[item["artifact"]["path"]]
        ).hexdigest()
    path = tmp_path / "scene-package.zip"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("scene-package.json", json.dumps(manifest))
        for name, content in artifacts.items():
            archive.writestr(name, content)
    return path


def test_scene_attachment_is_idempotent_and_replays_after_reopen(tmp_path) -> None:
    database = tmp_path / "agent-events.sqlite3"
    preview = ScenePackageArchive().inspect(_archive(tmp_path))
    store = AgentEventStore(database)
    store.create_run(
        "agent-run-001",
        budgets=AgentBudget(max_tool_calls=12, max_retries=2, max_cost_usd=0),
    )

    attached = store.attach_scene("agent-run-001", preview)
    duplicate = store.attach_scene("agent-run-001", preview)
    reopened = AgentEventStore(database).load("agent-run-001")

    assert attached == duplicate == reopened
    assert reopened.stage == "route_ready"
    assert reopened.scene is not None
    assert reopened.scene.archive_sha256 == preview.archive_sha256
    assert len(store.events("agent-run-001")) == 2
    status = reopened.status_bar()
    assert status.stage == "route_ready"
    assert status.scene_package_id == "coastal-ruins-ue-capture-001"
    assert status.budgets.max_tool_calls == 12
    assert status.pending_decision_count == 0
    assert len(status.artifact_ids) == 5


def test_pending_route_approval_survives_restart(tmp_path) -> None:
    database = tmp_path / "agent-events.sqlite3"
    preview = ScenePackageArchive().inspect(_archive(tmp_path))
    store = AgentEventStore(database)
    store.create_run("agent-run-approval")
    store.attach_scene("agent-run-approval", preview)
    pending = store.request_route_approval(
        "agent-run-approval",
        "route-local-001",
        "Use the reviewed local ComfyUI provider.",
        fingerprint="a" * 64,
    )

    reopened = AgentEventStore(database).load("agent-run-approval")
    assert pending == reopened
    assert reopened.stage == "awaiting_approval"
    assert reopened.approval == "pending"
    assert reopened.status_bar().pending_decision_count == 1
    approved = AgentEventStore(database).resolve_route_approval(
        "agent-run-approval", "route-local-001", "approved"
    )
    assert approved.stage == "approved"
    assert approved.approval == "approved"


def test_illegal_transition_and_expected_archive_hash_fail_closed(tmp_path) -> None:
    database = tmp_path / "agent-events.sqlite3"
    preview = ScenePackageArchive().inspect(_archive(tmp_path))
    store = AgentEventStore(database)
    store.create_run("agent-run-unsafe")

    with pytest.raises(AgentRuntimeError, match="cannot be requested"):
        store.request_route_approval("agent-run-unsafe", "route-001", "Too early")
    with pytest.raises(AgentRuntimeError, match="does not match"):
        store.attach_scene(
            "agent-run-unsafe",
            preview,
            expected_archive_sha256="0" * 64,
        )


def test_mutated_sqlite_event_is_detected_before_reduction(tmp_path) -> None:
    database = tmp_path / "agent-events.sqlite3"
    store = AgentEventStore(database)
    store.create_run("agent-run-corrupt")

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE agent_events SET data_json = ? WHERE run_id = ? AND sequence = 1",
            ('{"budgets":{"max_tool_calls":999}}', "agent-run-corrupt"),
        )
        connection.commit()

    with pytest.raises(AgentRuntimeError, match="hash does not match"):
        AgentEventStore(database).load("agent-run-corrupt")


def _comparison_plan(scene_sha256: str) -> ProviderComparisonPlan:
    return ProviderComparisonPlan(
        comparison_id="comparison-ui-run",
        dossier_id="dossier-fixture",
        dossier_sha256="d" * 64,
        scene_package_id="coastal-ruins-ue-capture-001",
        scene_package_sha256=scene_sha256,
        art_intent_sha256="b" * 64,
        children=[
            ComparisonChildPlan(
                role="local",
                action_id="local-comfy-generation",
                run_id="comparison-local-child",
                execution_id="comparison-local-execution",
                idempotency_key="comparison:ui:local",
                provider_id="comfy-local",
                model_id="flux-2-klein-base-4b-fp8",
                route_decision_id="route-local",
                route_fingerprint="1" * 64,
                attestation_environment_sha256="2" * 64,
                authority_kind="bounded_local_compute",
            ),
            ComparisonChildPlan(
                role="hosted",
                action_id="hosted-openai-edit",
                run_id="comparison-hosted-child",
                execution_id="comparison-hosted-execution",
                idempotency_key="comparison:ui:hosted",
                provider_id="openai-images",
                model_id="gpt-image-2-2026-04-21",
                route_decision_id="route-hosted",
                route_fingerprint="3" * 64,
                attestation_environment_sha256="4" * 64,
                authority_kind="hosted_privacy_cost",
            ),
        ],
        operator_preview=ComparisonOperatorPreview(
            local_uploads=["beauty"],
            hosted_uploads=["beauty"],
            hosted_endpoint="/v1/images/edits",
            hosted_model="gpt-image-2-2026-04-21",
            output_count_per_provider=1,
            output_size="1280x720",
            estimated_hosted_cost_usd=0.10,
            maximum_hosted_cost_usd=0.25,
            hosted_privacy_class="provider_retained",
            cost_cap_provider_enforced=False,
            unresolved_real_host_facts=["Fixture scene is not a real Unreal capture."],
        ),
    )


def test_comparison_lifecycle_is_content_bound_idempotent_and_replayable(tmp_path) -> None:
    database = tmp_path / "comparison-events.sqlite3"
    preview = ScenePackageArchive().inspect(_archive(tmp_path))
    store = AgentEventStore(database)
    store.create_run("comparison-ui-run")
    store.attach_scene("comparison-ui-run", preview)
    plan = _comparison_plan(preview.archive_sha256)

    planned = store.record_comparison_plan("comparison-ui-run", plan)
    duplicate = store.record_comparison_plan("comparison-ui-run", plan)
    assert planned == duplicate
    assert planned.pending_decisions[0].kind == "comparison_authorization"
    assert planned.pending_decisions[0].fingerprint == plan.approval_binding()

    wrong = ComparisonAuthorizationDecision(
        dossier_id=plan.dossier_id,
        dossier_sha256=plan.dossier_sha256,
        comparison_binding_sha256="f" * 64,
        resolution="approved",
        approved_by="human-owner",
        approved_at=datetime.now(UTC),
        authorized_action_ids=[
            child.action_id for child in plan.children if child.role == "hosted"
        ],
    )
    with pytest.raises(AgentRuntimeError, match="does not match"):
        store.record_comparison_authorization("comparison-ui-run", wrong)

    authorization = wrong.model_copy(
        update={"comparison_binding_sha256": plan.approval_binding()}
    )
    store.record_comparison_authorization("comparison-ui-run", authorization)
    manifest = ProviderComparisonManifest(
        comparison_id=plan.comparison_id,
        comparison_binding_sha256=plan.approval_binding(),
        scene_package_sha256=plan.scene_package_sha256,
        status="not_started",
        children=[
            ComparisonChildResult(
                role=child.role,
                run_id=child.run_id,
                execution_id=child.execution_id,
                provider_id=child.provider_id,
                model_id=child.model_id,
                status="not_started",
            )
            for child in plan.children
        ],
    )
    persisted = store.record_comparison_manifest("comparison-ui-run", manifest)
    reopened = AgentEventStore(database).load("comparison-ui-run")

    assert persisted == reopened
    assert reopened.comparison_plan == plan.model_dump(mode="json")
    assert reopened.comparison_authorization == authorization.model_dump(mode="json")
    assert reopened.comparison_manifest == manifest.model_dump(mode="json")
    assert len(store.events("comparison-ui-run")) == 5
