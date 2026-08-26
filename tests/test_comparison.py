import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.attestation import attest_hosted_contract_fixture, attest_local_capability
from artflow_agent.comfy_execution import (
    BoundedComfyAdapter,
    ComfyProviderAdapter,
    CompiledComfyRequest,
)
from artflow_agent.comparison import (
    ComparisonAuthorizationDecision,
    ComparisonBoundaryError,
    ComparisonPlanCompiler,
    ProviderComparisonLauncher,
)
from artflow_agent.contracts import RouteDecision, SceneConstraintPackage
from artflow_agent.contracts.provider import ProviderCapabilityManifest
from artflow_agent.domain import (
    EnvironmentSnapshot,
    OutputArtifact,
    QueuedJob,
    RecipeDefinition,
    UploadedInput,
)
from artflow_agent.hosted_execution import (
    CompiledHostedRequest,
    HostedAssetReference,
    HostedAuthorityGate,
    HostedAuthorityIssuer,
)
from artflow_agent.live_run import LiveRunAuthorizationDossier
from artflow_agent.openai_images import OpenAIImagesAdapter
from artflow_agent.scene_packages import ScenePackagePreview, VerifiedSceneArtifact

PNG = b"\x89PNG\r\n\x1a\ncomparison-source"
LOCAL_OUTPUT = b"\x89PNG\r\n\x1a\nlocal-output"
HOSTED_OUTPUT = b"\x89PNG\r\n\x1a\nhosted-output-with-provenance"


class _ComfyTransport:
    def __init__(self) -> None:
        self.uploads = 0
        self.queues = 0

    def upload_image(self, path: Path, *, subfolder: str) -> UploadedInput:
        self.uploads += 1
        return UploadedInput(name=path.name, subfolder=subfolder)

    def queue(self, _workflow, client_id=None) -> QueuedJob:
        self.queues += 1
        return QueuedJob(prompt_id="prompt-comparison-local", client_id=client_id)

    def history(self, _prompt_id: str):
        return {
            "status": {"completed": True},
            "outputs": {"18": {"images": [{"filename": "local.png", "subfolder": "ArtFlow"}]}},
        }

    def collect_outputs(self, _history):
        return [OutputArtifact(filename="local.png", subfolder="ArtFlow")]

    def fetch_output_bytes(self, _artifact: OutputArtifact) -> bytes:
        return LOCAL_OUTPUT


def _route(provider: str, scene: ScenePackagePreview) -> RouteDecision:
    hosted = provider == "openai-images"
    return RouteDecision(
        decision_id=f"route-{provider}",
        scene_package_id=scene.package.package_id,
        scene_package_sha256=scene.archive_sha256,
        task="scene_direction",
        selected={
            "provider_id": provider,
            "model_id": (
                "gpt-image-2-2026-04-21" if hosted else "flux-2-klein-base-4b-fp8"
            ),
            "execution_kind": "hosted" if hosted else "local",
            "privacy_class": "provider_retained" if hosted else "local_only",
            "cost_class": "metered" if hosted else "local_compute",
        },
        execution_intent={
            "required_controls": ["reference_image"],
            "evaluation_evidence": ["depth", "world_normal", "object_id"],
            "output_count": 1,
            "width": 1280,
            "height": 720,
            "delivery_format": "png",
            "intent_sha256": "b" * 64,
        },
        privacy_ceiling="provider_retained" if hosted else "local_only",
        max_cost_usd=0.25 if hosted else 0,
        requires_explicit_approval=True,
        rationale="Recorded comparison fixture.",
    )


def _canonical_sha(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _setup(
    tmp_path: Path,
    *,
    timeout_hosted: bool = False,
    hosted_supported: bool = True,
):
    root = Path(__file__).parents[1]
    package = SceneConstraintPackage.model_validate_json(
        (root / "examples" / "scene-constraint-package.example.json").read_text()
    )
    pass_contents = {
        "beauty": PNG,
        "depth": b"depth",
        "world_normal": b"normal",
        "object_id": b"object",
    }
    passes = []
    artifacts = []
    for scene_pass in package.passes:
        content = pass_contents[scene_pass.kind]
        digest = hashlib.sha256(content).hexdigest()
        artifact = scene_pass.artifact.model_copy(update={"sha256": digest})
        passes.append(scene_pass.model_copy(update={"artifact": artifact}))
        artifacts.append(
            VerifiedSceneArtifact(path=artifact.path, sha256=digest, size_bytes=len(content))
        )
    package = package.model_copy(update={"passes": passes})
    scene = ScenePackagePreview(
        package=package,
        archive_sha256="a" * 64,
        artifacts=artifacts,
    )
    local_decision = _route("comfy-local", scene)
    hosted_decision = _route("openai-images", scene)

    local_manifest = ProviderCapabilityManifest(
        provider_id="comfy-local",
        display_name="Recorded local fixture",
        execution_kind="local",
        privacy_class="local_only",
        cost_class="local_compute",
        requires_explicit_cost_approval=False,
        models=[{
            "model_id": "flux-2-klein-base-4b-fp8",
            "model_version": "fixture",
            "tasks": ["scene_direction"],
            "controls": ["reference_image"],
        }],
    )
    recipe = RecipeDefinition(
        recipe_id="composition-preserving-v1",
        version="1.1.0",
        task_type="scene_direction",
        description="fixture",
        workflow_file="fixture.json",
        execution_ready=True,
        consumed_controls=["reference_image"],
        slots=[],
    )
    local_attestation = attest_local_capability(
        EnvironmentSnapshot(
            comfy_url="http://127.0.0.1:8188",
            reachable=True,
            vram_mb=16000,
        ),
        local_manifest,
        "flux-2-klein-base-4b-fp8",
        recipe,
    )
    hosted_attestation = attest_hosted_contract_fixture(
        provider_id="openai-images",
        model_id="gpt-image-2-2026-04-21",
        contract_version="recorded-2026-08-25",
        privacy_class="provider_retained",
        max_cost_usd=0.25,
        fixture_supported=hosted_supported,
    )
    dossier = LiveRunAuthorizationDossier.load(
        root / "artifacts" / "goal" / "m3-s6-live-run-authorization.json"
    ).model_copy(
        update={"local_attestation_sha256": local_attestation.environment_sha256}
    )
    plan = ComparisonPlanCompiler.compile(
        dossier,
        comparison_id="comparison-001",
        local_run_id="comparison-local-run",
        hosted_run_id="comparison-hosted-run",
        local_decision=local_decision,
        hosted_decision=hosted_decision,
        local_attestation_sha256=local_attestation.environment_sha256,
        hosted_attestation_sha256=hosted_attestation.environment_sha256,
        estimated_hosted_cost_usd=0.10,
    )
    store = AgentEventStore(tmp_path / "events.sqlite3")
    for child, decision, attestation in (
        (plan.children[0], local_decision, local_attestation),
        (plan.children[1], hosted_decision, hosted_attestation),
    ):
        store.create_run(child.run_id)
        store.attach_scene(child.run_id, scene)
        store.propose_route(child.run_id, decision)
        store.record_capability_attestation(child.run_id, attestation)
        store.resolve_route_approval(child.run_id, decision.decision_id, "approved")
        if attestation.status == "supported":
            store.reserve_provider_execution(
                child.run_id, child.execution_id, child.idempotency_key, decision
            )

    local_child, hosted_child = plan.children
    source = tmp_path / "beauty.png"
    source.write_bytes(PNG)
    local_compiled = CompiledComfyRequest(
        run_id=local_child.run_id,
        execution_id=local_child.execution_id,
        route_decision_id=local_child.route_decision_id,
        route_fingerprint=local_child.route_fingerprint,
        provider_id=local_child.provider_id,
        model_id=local_child.model_id,
        scene_package_id=scene.package.package_id,
        scene_package_sha256=scene.archive_sha256,
        attestation_environment_sha256=local_child.attestation_environment_sha256,
        recipe_id="composition-preserving-v1",
        recipe_version="1.1.0",
        workflow_sha256="d" * 64,
        source_artifact_path="passes/beauty.png",
        source_artifact_sha256=hashlib.sha256(PNG).hexdigest(),
        workflow={"1": {"class_type": "Fixture", "inputs": {}}},
    )
    hosted_compiled = CompiledHostedRequest(
        run_id=hosted_child.run_id,
        execution_id=hosted_child.execution_id,
        idempotency_key=hosted_child.idempotency_key,
        route_decision_id=hosted_child.route_decision_id,
        route_fingerprint=hosted_child.route_fingerprint,
        provider_id=hosted_child.provider_id,
        model_id=hosted_child.model_id,
        scene_package_id=scene.package.package_id,
        scene_package_sha256=scene.archive_sha256,
        attestation_environment_sha256=hosted_child.attestation_environment_sha256,
        privacy_class="provider_retained",
        approved_max_cost_usd=0.25,
        estimated_cost_usd=0.10,
        width=1280,
        height=720,
        output_count=1,
        art_goal="Preserve composition and improve material direction.",
        preserve=["camera", "silhouette"],
        prohibit=["new objects"],
        assets=[HostedAssetReference(
            role="reference_image",
            package_path="passes/beauty.png",
            sha256=hashlib.sha256(PNG).hexdigest(),
            media_type="image/png",
        )],
    )
    secret = b"q" * 32
    hosted_gate = HostedAuthorityGate(tmp_path / "authorities.sqlite3", secret)
    expires = datetime.now(UTC) + timedelta(minutes=5)
    hosted_authority = HostedAuthorityIssuer(secret).issue(hosted_compiled, expires)
    transport = _ComfyTransport()
    local_provider = ComfyProviderAdapter(
        local_compiled,
        adapter=BoundedComfyAdapter(transport),
        source_path=source,
        idempotency_key=local_child.idempotency_key,
    )
    hosted_calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        hosted_calls["count"] += 1
        if timeout_hosted:
            raise httpx.ReadTimeout("response lost", request=request)
        return httpx.Response(
            200,
            headers={"x-request-id": "req-comparison-hosted"},
            json={"data": [{"b64_json": base64.b64encode(HOSTED_OUTPUT).decode()}]},
        )

    hosted_provider = OpenAIImagesAdapter(
        hosted_compiled,
        authority=hosted_authority,
        gate=hosted_gate,
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://api.openai.com"
        ),
        api_key="recorded-fixture-key",
        content_by_sha256={hashlib.sha256(PNG).hexdigest(): PNG},
    )
    authorization = ComparisonAuthorizationDecision(
        dossier_id=dossier.dossier_id,
        dossier_sha256=_canonical_sha(dossier.model_dump(mode="json")),
        comparison_binding_sha256=plan.approval_binding(),
        resolution="approved",
        approved_by="fixture-human-owner",
        approved_at=datetime.now(UTC),
        authorized_action_ids=[
            child.action_id for child in plan.children if child.role == "hosted"
        ],
    )
    return {
        "store": store,
        "plan": plan,
        "dossier": dossier,
        "authorization": authorization,
        "local_decision": local_decision,
        "hosted_decision": hosted_decision,
        "local_compiled": local_compiled,
        "hosted_compiled": hosted_compiled,
        "hosted_authority": hosted_authority,
        "hosted_gate": hosted_gate,
        "local_provider": local_provider,
        "hosted_provider": hosted_provider,
        "transport": transport,
        "hosted_calls": hosted_calls,
    }


def _launch(values, **overrides):
    arguments = {
        "plan": values["plan"],
        "dossier": values["dossier"],
        "authorization": values["authorization"],
        "local_decision": values["local_decision"],
        "hosted_decision": values["hosted_decision"],
        "local_compiled": values["local_compiled"],
        "hosted_compiled": values["hosted_compiled"],
        "hosted_authority": values["hosted_authority"],
        "hosted_gate": values["hosted_gate"],
        "local_provider": values["local_provider"],
        "hosted_provider": values["hosted_provider"],
    }
    arguments.update(overrides)
    return ProviderComparisonLauncher(values["store"]).launch_or_resume(**arguments)


def test_recorded_dual_provider_launch_normalizes_one_unselected_manifest(tmp_path) -> None:
    values = _setup(tmp_path)
    manifest = _launch(values)

    assert manifest.status == "succeeded"
    assert {child.status for child in manifest.children} == {"succeeded"}
    assert manifest.human_selected_candidate_id is None
    assert values["transport"].uploads == values["transport"].queues == 1
    assert values["hosted_calls"]["count"] == 1
    assert manifest.children[1].receipt.provider_request_id == "req-comparison-hosted"
    assert manifest.children[1].receipt.artifacts[0].sha256 == hashlib.sha256(
        HOSTED_OUTPUT
    ).hexdigest()

    replayed = _launch(
        values,
        authorization=None,
        hosted_authority=None,
    )
    assert replayed == manifest
    assert values["transport"].queues == 1
    assert values["hosted_calls"]["count"] == 1


@pytest.mark.parametrize("missing", ["authorization", "hosted_authority"])
def test_missing_hosted_authority_fails_before_either_side_effect(
    tmp_path, missing
) -> None:
    values = _setup(tmp_path)
    with pytest.raises(ComparisonBoundaryError):
        _launch(values, **{missing: None})
    assert values["transport"].uploads == values["transport"].queues == 0
    assert values["hosted_calls"]["count"] == 0


def test_unknown_hosted_completion_is_not_retried_or_presented_as_complete(tmp_path) -> None:
    values = _setup(tmp_path, timeout_hosted=True)
    manifest = _launch(values)
    assert manifest.status == "needs_human_recovery"
    assert [child.status for child in manifest.children] == [
        "succeeded",
        "completion_unknown",
    ]
    assert manifest.human_selected_candidate_id is None
    assert values["hosted_calls"]["count"] == 1

    replayed = _launch(
        values,
        authorization=None,
        hosted_authority=None,
    )
    assert replayed.status == "needs_human_recovery"
    assert values["transport"].queues == 1
    assert values["hosted_calls"]["count"] == 1


def test_unsupported_child_attestation_fails_before_local_side_effect(tmp_path) -> None:
    values = _setup(tmp_path, hosted_supported=False)
    with pytest.raises(ComparisonBoundaryError, match="attestation"):
        _launch(values)
    assert values["transport"].uploads == values["transport"].queues == 0
    assert values["hosted_calls"]["count"] == 0
