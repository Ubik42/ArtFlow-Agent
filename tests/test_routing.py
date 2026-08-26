import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from artflow_agent.agent_projection import project_agent_run
from artflow_agent.agent_runtime import AgentEventStore, AgentRuntimeError
from artflow_agent.attestation import attest_local_capability
from artflow_agent.contracts import ProviderCapabilityManifest
from artflow_agent.domain import EnvironmentSnapshot, RecipeDefinition
from artflow_agent.routing import (
    ProviderRouteCandidate,
    RoutePolicyError,
    RoutePolicyRequest,
    route_scene_package,
)
from artflow_agent.scene_packages import ScenePackageArchive


def _preview(tmp_path: Path):
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
    archive_path = tmp_path / "route-scene.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("scene-package.json", json.dumps(manifest))
        for name, content in artifacts.items():
            archive.writestr(name, content)
    return ScenePackageArchive().inspect(archive_path)


def _manifest(provider_id: str, *, hosted: bool) -> ProviderCapabilityManifest:
    return ProviderCapabilityManifest(
        provider_id=provider_id,
        display_name=provider_id,
        execution_kind="hosted" if hosted else "local",
        privacy_class="provider_processed" if hosted else "local_only",
        cost_class="metered" if hosted else "local_compute",
        requires_explicit_cost_approval=hosted,
        models=[
            {
                "model_id": "frontier-edit" if hosted else "flux-depth-local",
                "model_version": "fixture-1",
                "tasks": ["scene_direction"],
                "controls": ["reference_image"],
                "max_reference_images": 4,
            }
        ],
    )


def test_matched_providers_are_filtered_ranked_and_explained(tmp_path) -> None:
    preview = _preview(tmp_path)
    local = ProviderRouteCandidate(
        manifest=_manifest("comfy-local", hosted=False),
        model_id="flux-depth-local",
        availability="supported",
        estimated_cost_usd=0,
    )
    hosted = ProviderRouteCandidate(
        manifest=_manifest("frontier-image", hosted=True),
        model_id="frontier-edit",
        availability="supported",
        estimated_cost_usd=0.08,
    )
    unknown = hosted.model_copy(
        update={"manifest": _manifest("unprobed-hosted", hosted=True), "availability": "unknown"}
    )

    result = route_scene_package(
        preview,
        [hosted, unknown, local],
        RoutePolicyRequest(
            decision_id="route-matched-001",
            privacy_ceiling="provider_processed",
            max_cost_usd=0.10,
            output_width=1024,
            output_height=576,
        ),
    )

    assert result.evaluated_count == 3
    assert result.eligible_count == 2
    assert result.decision.selected.provider_id == "comfy-local"
    assert result.decision.execution_intent.required_controls == ["reference_image"]
    assert result.decision.execution_intent.width == 1024
    assert result.decision.execution_intent.height == 576
    assert result.decision.execution_intent.evaluation_evidence == [
        "depth",
        "world_normal",
        "object_id",
    ]
    reasons = {item.provider_id: item.reasons for item in result.decision.rejected}
    assert reasons["unprobed-hosted"] == ["availability_unknown"]
    assert "lower_deterministic_policy_rank" in reasons["frontier-image"]
    assert "higher_privacy_exposure" in reasons["frontier-image"]


def test_local_route_auto_accepts_and_changed_execution_intent_loses_integrity(tmp_path) -> None:
    preview = _preview(tmp_path)
    result = route_scene_package(
        preview,
        [
            ProviderRouteCandidate(
                manifest=_manifest("comfy-local", hosted=False),
                model_id="flux-depth-local",
                availability="supported",
                estimated_cost_usd=0,
            )
        ],
        RoutePolicyRequest(decision_id="route-authority-001"),
    )
    database = tmp_path / "route-events.sqlite3"
    store = AgentEventStore(database)
    store.create_run("route-agent-run")
    store.attach_scene("route-agent-run", preview)
    proposed = store.propose_route("route-agent-run", result.decision)

    assert proposed.stage == "approved"
    assert proposed.route_decision == result.decision
    assert proposed.pending_decisions == []
    approved = proposed
    assert approved.status_bar().route_provider == "comfy-local"
    projection = project_agent_run(AgentEventStore(database), "route-agent-run")
    assert projection.route is not None
    assert projection.route.provider_id == "comfy-local"
    assert projection.timeline[-1].event_type == "route_proposed"
    AgentEventStore(database).assert_route_authorized("route-agent-run", result.decision)

    attestation = attest_local_capability(
        EnvironmentSnapshot(
            comfy_url="http://127.0.0.1:8188",
            reachable=True,
            vram_mb=16000,
            nodes=["LoadImage"],
            models=["model.safetensors"],
        ),
        _manifest("comfy-local", hosted=False),
        "flux-depth-local",
        RecipeDefinition(
            recipe_id="route-recipe",
            version="1",
            task_type="scene_direction",
            description="fixture",
            workflow_file="fixture.json",
            execution_ready=True,
            required_models=["model.safetensors"],
            required_nodes=["LoadImage"],
            estimated_vram_mb=8000,
            slots=[],
        ),
    )
    replayed = AgentEventStore(database).record_capability_attestation(
        "route-agent-run", attestation
    )
    assert replayed.status_bar().local_provider_status == "supported"
    assert project_agent_run(AgentEventStore(database), "route-agent-run").capability_attestations
    event_count = len(AgentEventStore(database).events("route-agent-run"))
    duplicate = AgentEventStore(database).record_capability_attestation(
        "route-agent-run", attestation.model_copy(update={"attestation_id": "attestation-new"})
    )
    assert len(AgentEventStore(database).events("route-agent-run")) == event_count
    assert duplicate.capability_attestations == replayed.capability_attestations

    changed_cost = result.decision.model_copy(update={"max_cost_usd": 1})
    with pytest.raises(AgentRuntimeError, match="fingerprint does not match"):
        AgentEventStore(database).assert_route_authorized("route-agent-run", changed_cost)


def test_no_supported_route_fails_closed(tmp_path) -> None:
    preview = _preview(tmp_path)
    candidate = ProviderRouteCandidate(
        manifest=_manifest("unavailable-hosted", hosted=True),
        model_id="frontier-edit",
        availability="unknown",
        estimated_cost_usd=0.08,
    )
    with pytest.raises(RoutePolicyError, match="availability_unknown"):
        route_scene_package(
            preview,
            [candidate],
            RoutePolicyRequest(
                decision_id="route-none-001",
                privacy_ceiling="provider_processed",
                max_cost_usd=1,
            ),
        )


def test_route_output_size_must_be_an_explicit_pair(tmp_path) -> None:
    with pytest.raises(ValueError, match="must be supplied together"):
        RoutePolicyRequest(decision_id="route-size-001", output_width=1024)
