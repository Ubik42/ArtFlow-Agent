import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from artflow_agent.agent_runtime import AgentEventStore, AgentRuntimeError
from artflow_agent.attestation import attest_local_capability
from artflow_agent.codex_image_ingress import import_codex_image_candidate
from artflow_agent.contracts import ProviderExecutionReceipt, ReceiptArtifact, RouteDecision
from artflow_agent.contracts.provider import ProviderCapabilityManifest
from artflow_agent.domain import ArtBrief, Candidate, EnvironmentSnapshot, RecipeDefinition
from artflow_agent.planning import DeterministicPlanner
from artflow_agent.run_store import RunStore
from artflow_agent.scene_packages import ScenePackageArchive
from artflow_agent.web_api import create_app


def _scene_archive(tmp_path: Path, *, corrupt: str | None = None) -> Path:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "examples" / "scene-constraint-package.example.json").read_text(
            encoding="utf-8"
        )
    )
    manifest["provenance"]["scene_name"] = "/Game/ArtFlowDemo"
    artifacts = {
        "passes/beauty.png": b"real-beauty",
        "passes/depth.exr": b"real-depth",
        "passes/world-normal.exr": b"real-world-normal",
        "passes/object-id.png": b"real-object-id",
    }
    for item in manifest["passes"]:
        item["artifact"]["sha256"] = hashlib.sha256(
            artifacts[item["artifact"]["path"]]
        ).hexdigest()
    path = tmp_path / ("corrupt.zip" if corrupt else "scene.zip")
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("scene-package.json", json.dumps(manifest))
        for name, content in artifacts.items():
            archive.writestr(name, b"tampered" if name == corrupt else content)
    return path


def test_web_api_preserves_approval_gate(tmp_path) -> None:
    brief = ArtBrief(
        project_name="fixture",
        source_image="examples/assets/coastal-ruins-graybox.png",
        intent="Create one controlled environment lighting direction.",
        variant_count=1,
    )
    store = RunStore(tmp_path)
    store.create(brief, DeterministicPlanner().create_plan(brief), run_id="run")
    client = TestClient(create_app(runs_dir=tmp_path))

    assert client.get("/api/runs").json()[0]["run_id"] == "run"
    blocked = client.post("/api/runs/run/execute", json={})
    assert blocked.status_code == 409
    assert "requires approval" in blocked.json()["detail"]

    approved = client.post("/api/runs/run/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_candidate_artifact_survives_repository_move_without_rewriting_state(tmp_path) -> None:
    brief = ArtBrief(
        project_name="fixture",
        source_image="examples/assets/coastal-ruins-graybox.png",
        intent="Create one controlled environment lighting direction.",
        variant_count=1,
    )
    store = RunStore(tmp_path)
    store.create(brief, DeterministicPlanner().create_plan(brief), run_id="run")
    store.approve("run")
    store.mark_running("run")
    artifact = tmp_path / "run" / "artifacts" / "direction" / "result.png"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"portable-result")
    store.set_candidates(
        "run",
        [
            Candidate(
                candidate_id="candidate-01",
                direction_name="direction",
                image_path=r"D:\old-location\ArtFlow-Agent\runs\run\artifacts\direction\result.png",
            )
        ],
    )

    client = TestClient(create_app(runs_dir=tmp_path))
    response = client.get("/api/runs/run/candidates/candidate-01")

    assert response.status_code == 200
    assert response.content == b"portable-result"


def test_scene_package_import_is_verified_persisted_and_read_only(tmp_path) -> None:
    archive_path = _scene_archive(tmp_path)
    payload = archive_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    runs_dir = tmp_path / "runs"
    client = TestClient(create_app(runs_dir=runs_dir))

    response = client.post(
        "/api/agent/scene-packages/import",
        content=payload,
        headers={
            "Content-Type": "application/zip",
            "X-Scene-Package-SHA256": digest,
        },
    )

    assert response.status_code == 200
    scene = response.json()["scene"]
    assert scene["archive_sha256"] == digest
    assert scene["artifact_count"] == 4
    assert scene["evidence_class"] == "real_unreal_capture"
    run_id = response.json()["run_id"]
    assert (runs_dir / ".agent-artifacts" / "scene-packages" / f"{digest}.zip").is_file()
    beauty = client.get(f"/api/agent/runs/{run_id}/scene/passes/beauty")
    assert beauty.status_code == 200
    assert beauty.content == b"real-beauty"
    assert beauty.headers["x-content-sha256"] == hashlib.sha256(b"real-beauty").hexdigest()

    duplicate = client.post(
        "/api/agent/scene-packages/import",
        content=payload,
        headers={"Content-Type": "application/zip"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["run_id"] == run_id
    assert len(duplicate.json()["timeline"]) == 2


def test_scene_package_import_rejects_tamper_before_creating_run(tmp_path) -> None:
    client = TestClient(create_app(runs_dir=tmp_path / "runs"))
    response = client.post(
        "/api/agent/scene-packages/import",
        content=_scene_archive(tmp_path, corrupt="passes/depth.exr").read_bytes(),
        headers={"Content-Type": "application/zip"},
    )

    assert response.status_code == 400
    assert "hash mismatch" in response.json()["detail"]
    assert client.get("/api/agent/runs").json() == []


def test_verified_provider_artifact_is_served_by_receipt_hash(tmp_path) -> None:
    preview = ScenePackageArchive().inspect(_scene_archive(tmp_path))
    database = tmp_path / "agent-events.sqlite3"
    store = AgentEventStore(database)
    store.create_run("real-local-run")
    store.attach_scene("real-local-run", preview)
    decision = RouteDecision(
        decision_id="route-real-local",
        scene_package_id=preview.package.package_id,
        scene_package_sha256=preview.archive_sha256,
        task="scene_direction",
        selected={
            "provider_id": "comfy-local",
            "model_id": "flux-local",
            "execution_kind": "local",
            "privacy_class": "local_only",
            "cost_class": "local_compute",
        },
        execution_intent={
            "required_controls": ["reference_image"],
            "width": 1024,
            "height": 576,
            "delivery_format": "png",
            "intent_sha256": "a" * 64,
        },
        privacy_ceiling="local_only",
        max_cost_usd=0,
        requires_explicit_approval=False,
        rationale="Bounded local route",
    )
    store.propose_route("real-local-run", decision)
    manifest = ProviderCapabilityManifest(
        provider_id="comfy-local",
        display_name="Local",
        execution_kind="local",
        privacy_class="local_only",
        cost_class="local_compute",
        requires_explicit_cost_approval=False,
        models=[{
            "model_id": "flux-local",
            "model_version": "fixture",
            "tasks": ["scene_direction"],
            "controls": ["reference_image"],
        }],
    )
    attestation = attest_local_capability(
        EnvironmentSnapshot(
            comfy_url="http://127.0.0.1:8188",
            reachable=True,
            vram_mb=16000,
            nodes=["LoadImage"],
            models=["fixture.safetensors"],
        ),
        manifest,
        "flux-local",
        RecipeDefinition(
            recipe_id="fixture-recipe",
            version="1",
            task_type="scene_direction",
            description="fixture",
            workflow_file="fixture.json",
            execution_ready=True,
            consumed_controls=["reference_image"],
            required_models=["fixture.safetensors"],
            required_nodes=["LoadImage"],
            slots=[],
        ),
    )
    store.record_capability_attestation("real-local-run", attestation)
    store.reserve_provider_execution(
        "real-local-run", "execution-local", "local-once", decision
    )
    store.record_provider_submission("real-local-run", "execution-local", "prompt-real")
    content = b"verified-local-candidate"
    digest = hashlib.sha256(content).hexdigest()
    now = datetime.now(UTC)
    store.record_provider_receipt(
        "real-local-run",
        ProviderExecutionReceipt(
            execution_id="execution-local",
            route_decision_id=decision.decision_id,
            route_fingerprint=decision.approval_fingerprint(),
            provider_id="comfy-local",
            model_id="flux-local",
            status="succeeded",
            started_at=now,
            completed_at=now,
            provider_request_id="prompt-real",
            artifacts=[ReceiptArtifact(path="candidate.png", sha256=digest, media_type="image/png")],
        ),
    )
    root = tmp_path / ".agent-artifacts" / "provider-outputs"
    root.mkdir(parents=True)
    (root / f"{digest}.png").write_bytes(content)
    client = TestClient(create_app(runs_dir=tmp_path / "runs", agent_database=database))

    response = client.get(
        f"/api/agent/runs/real-local-run/executions/execution-local/artifacts/{digest}"
    )
    assert response.status_code == 200
    assert response.content == content
    assert response.headers["x-content-sha256"] == digest

    (root / f"{digest}.png").write_bytes(b"tampered")
    rejected = client.get(
        f"/api/agent/runs/real-local-run/executions/execution-local/artifacts/{digest}"
    )
    assert rejected.status_code == 409


def test_codex_candidate_import_is_bound_idempotent_and_tamper_evident(tmp_path) -> None:
    preview = ScenePackageArchive().inspect(_scene_archive(tmp_path))
    database = tmp_path / "agent-events.sqlite3"
    store = AgentEventStore(database)
    store.create_run("codex-boundary-run")
    store.attach_scene("codex-boundary-run", preview)
    decision = RouteDecision(
        decision_id="route-codex-source",
        scene_package_id=preview.package.package_id,
        scene_package_sha256=preview.archive_sha256,
        task="scene_direction",
        selected={
            "provider_id": "comfy-local",
            "model_id": "flux-local",
            "execution_kind": "local",
            "privacy_class": "local_only",
            "cost_class": "local_compute",
        },
        execution_intent={
            "required_controls": ["reference_image"],
            "width": 1024,
            "height": 576,
            "delivery_format": "png",
            "intent_sha256": "b" * 64,
        },
        privacy_ceiling="local_only",
        max_cost_usd=0,
        requires_explicit_approval=False,
        rationale="Bounded source route",
    )
    store.propose_route("codex-boundary-run", decision)
    manifest = ProviderCapabilityManifest(
        provider_id="comfy-local",
        display_name="Local",
        execution_kind="local",
        privacy_class="local_only",
        cost_class="local_compute",
        requires_explicit_cost_approval=False,
        models=[{
            "model_id": "flux-local",
            "model_version": "fixture",
            "tasks": ["scene_direction"],
            "controls": ["reference_image"],
        }],
    )
    attestation = attest_local_capability(
        EnvironmentSnapshot(
            comfy_url="http://127.0.0.1:8188",
            reachable=True,
            vram_mb=16000,
            nodes=["LoadImage"],
            models=["fixture.safetensors"],
        ),
        manifest,
        "flux-local",
        RecipeDefinition(
            recipe_id="fixture-recipe",
            version="1",
            task_type="scene_direction",
            description="fixture",
            workflow_file="fixture.json",
            execution_ready=True,
            consumed_controls=["reference_image"],
            required_models=["fixture.safetensors"],
            required_nodes=["LoadImage"],
            slots=[],
        ),
    )
    store.record_capability_attestation("codex-boundary-run", attestation)
    store.reserve_provider_execution(
        "codex-boundary-run", "source-execution", "source-once", decision
    )
    store.record_provider_submission("codex-boundary-run", "source-execution", "source-prompt")
    now = datetime.now(UTC)
    store.record_provider_receipt(
        "codex-boundary-run",
        ProviderExecutionReceipt(
            execution_id="source-execution",
            route_decision_id=decision.decision_id,
            route_fingerprint=decision.approval_fingerprint(),
            provider_id="comfy-local",
            model_id="flux-local",
            status="succeeded",
            started_at=now,
            completed_at=now,
            provider_request_id="source-prompt",
            artifacts=[
                ReceiptArtifact(path="source.png", sha256="c" * 64, media_type="image/png")
            ],
        ),
    )
    candidate_path = tmp_path / "codex-output.png"
    Image.new("RGB", (128, 72), color=(20, 40, 60)).save(candidate_path)
    artifact_root = tmp_path / ".agent-artifacts" / "provider-outputs"
    beauty_sha256 = next(
        item.artifact.sha256 for item in preview.package.passes if item.kind == "beauty"
    )

    with pytest.raises(AgentRuntimeError, match="source binding"):
        import_codex_image_candidate(
            store,
            "codex-boundary-run",
            candidate_path,
            "bounded prompt",
            artifact_root=artifact_root,
            expected_archive_sha256="0" * 64,
            expected_beauty_sha256=beauty_sha256,
        )

    first = import_codex_image_candidate(
        store,
        "codex-boundary-run",
        candidate_path,
        "bounded prompt",
        artifact_root=artifact_root,
        expected_archive_sha256=preview.archive_sha256,
        expected_beauty_sha256=beauty_sha256,
    )
    duplicate = import_codex_image_candidate(
        AgentEventStore(database),
        "codex-boundary-run",
        candidate_path,
        "bounded prompt",
        artifact_root=artifact_root,
        expected_archive_sha256=preview.archive_sha256,
        expected_beauty_sha256=beauty_sha256,
    )
    assert first == duplicate
    assert len(store.events("codex-boundary-run")) == 8
    assert store.load("codex-boundary-run").pending_decisions == []

    artifact = first.receipt.artifact
    client = TestClient(create_app(runs_dir=tmp_path / "runs", agent_database=database))
    url = (
        f"/api/agent/runs/codex-boundary-run/codex-candidates/"
        f"{first.receipt.candidate_id}/artifacts/{artifact.sha256}"
    )
    response = client.get(url)
    assert response.status_code == 200
    assert response.headers["x-content-sha256"] == artifact.sha256

    (artifact_root / f"{artifact.sha256}.png").write_bytes(b"tampered")
    assert client.get(url).status_code == 409
