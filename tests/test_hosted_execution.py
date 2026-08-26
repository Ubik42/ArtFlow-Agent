import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.attestation import attest_hosted_contract_fixture
from artflow_agent.contracts import SceneConstraintPackage
from artflow_agent.contracts.provider import ProviderCapabilityManifest
from artflow_agent.hosted_execution import (
    HostedAuthorityGate,
    HostedAuthorityIssuer,
    HostedExecutionBoundaryError,
    HostedProviderAdapter,
    HostedRequestCompiler,
)
from artflow_agent.provider_execution import ProviderExecutionCoordinator
from artflow_agent.routing import ProviderRouteCandidate, RoutePolicyRequest, route_scene_package
from artflow_agent.scene_packages import ScenePackagePreview, VerifiedSceneArtifact


def _prepared_hosted_run(tmp_path: Path):
    root = Path(__file__).parents[1]
    package = SceneConstraintPackage.model_validate_json(
        (root / "examples" / "scene-constraint-package.example.json").read_text(
            encoding="utf-8"
        )
    )
    contents: dict[str, bytes] = {}
    passes = []
    artifacts = []
    for scene_pass in package.passes:
        content = f"fixture:{scene_pass.kind}".encode()
        digest = hashlib.sha256(content).hexdigest()
        artifact = scene_pass.artifact.model_copy(update={"sha256": digest})
        passes.append(scene_pass.model_copy(update={"artifact": artifact}))
        artifacts.append(
            VerifiedSceneArtifact(path=artifact.path, sha256=digest, size_bytes=len(content))
        )
        contents[digest] = content
    package = package.model_copy(update={"passes": passes})
    preview = ScenePackagePreview(
        package=package,
        archive_sha256="a" * 64,
        artifacts=artifacts,
    )
    manifest = ProviderCapabilityManifest(
        provider_id="hosted-fixture",
        display_name="Recorded hosted fixture",
        execution_kind="hosted",
        privacy_class="provider_processed",
        cost_class="metered",
        requires_explicit_cost_approval=True,
        models=[
            {
                "model_id": "fixture-edit-v1",
                "model_version": "recorded-contract-1",
                "tasks": ["scene_direction"],
                "controls": ["reference_image"],
            }
        ],
    )
    decision = route_scene_package(
        preview,
        [
            ProviderRouteCandidate(
                manifest=manifest,
                model_id="fixture-edit-v1",
                availability="supported",
                estimated_cost_usd=0.08,
            )
        ],
        RoutePolicyRequest(
            decision_id="route-hosted-001",
            privacy_ceiling="provider_processed",
            max_cost_usd=0.10,
            prefer_local=False,
        ),
    ).decision
    database = tmp_path / "events.sqlite3"
    store = AgentEventStore(database)
    store.create_run("hosted-run-001")
    store.attach_scene("hosted-run-001", preview)
    store.propose_route("hosted-run-001", decision)
    store.record_capability_attestation(
        "hosted-run-001",
        attest_hosted_contract_fixture(
            provider_id="hosted-fixture",
            model_id="fixture-edit-v1",
            contract_version="recorded-contract-1",
            privacy_class="provider_processed",
            max_cost_usd=0.10,
            fixture_supported=True,
        ),
    )
    store.resolve_route_approval("hosted-run-001", decision.decision_id, "approved")
    store.reserve_provider_execution(
        "hosted-run-001",
        "hosted-execution-001",
        "hosted:idem:001",
        decision,
    )
    compiled = HostedRequestCompiler(store).compile(
        "hosted-run-001", "hosted-execution-001", estimated_cost_usd=0.08
    )
    return database, decision, compiled, contents


def test_hosted_adapter_runs_through_durable_ledger_with_redacted_http(tmp_path) -> None:
    database, decision, compiled, contents = _prepared_hosted_run(tmp_path)
    result = b"hosted-result"
    result_sha = hashlib.sha256(result).hexdigest()
    provider_state = {"submitted": False, "terminal": False}
    observed_payload = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_payload
        if request.method == "GET" and "by-idempotency" in request.url.path:
            if not provider_state["submitted"]:
                return httpx.Response(404)
            status = "succeeded" if provider_state["terminal"] else "running"
            body = {
                "id": "hosted-job-001",
                "status": status,
                "cost_usd": 0.08,
                "metadata": compiled.redacted_payload(contents)["metadata"],
            }
            if status == "succeeded":
                body["outputs"] = [
                    {
                        "filename": "result.png",
                        "sha256": result_sha,
                        "media_type": "image/png",
                    }
                ]
            return httpx.Response(200, json=body)
        if request.method == "POST" and request.url.path == "/v1/image-edits":
            assert request.headers["Idempotency-Key"] == "hosted:idem:001"
            assert request.headers["Authorization"] == "Bearer fixture-secret"
            observed_payload = json.loads(request.content)
            provider_state["submitted"] = True
            return httpx.Response(202, json={"id": "hosted-job-001"})
        if request.method == "GET" and request.url.path.endswith("/outputs/result.png"):
            return httpx.Response(200, content=result)
        raise AssertionError(f"Unexpected request: {request.method} {request.url.path}")

    secret = b"h" * 32
    authority = HostedAuthorityIssuer(secret).issue(
        compiled, datetime.now(UTC) + timedelta(minutes=5)
    )
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://fixture.invalid")
    adapter = HostedProviderAdapter(
        compiled,
        authority=authority,
        gate=HostedAuthorityGate(tmp_path / "authority.sqlite3", secret),
        client=client,
        api_key="fixture-secret",
        content_by_sha256=contents,
    )
    unknown = ProviderExecutionCoordinator(AgentEventStore(database), adapter).run_or_reconcile(
        "hosted-run-001",
        "hosted-execution-001",
        "hosted:idem:001",
        decision,
    )
    assert unknown.stage == "reconciling"
    assert observed_payload is not None
    assert set(observed_payload) == {
        "model",
        "prompt",
        "preserve",
        "prohibit",
        "width",
        "height",
        "output_count",
        "assets",
        "metadata",
    }
    assert "source_scene" not in json.dumps(observed_payload)
    assert "protected_regions" not in json.dumps(observed_payload)

    provider_state["terminal"] = True
    completed = ProviderExecutionCoordinator(
        AgentEventStore(database), adapter
    ).run_or_reconcile(
        "hosted-run-001",
        "hosted-execution-001",
        "hosted:idem:001",
        decision,
    )
    assert completed.stage == "execution_succeeded"
    assert completed.provider_executions[0].receipt.artifacts[0].sha256 == result_sha


@pytest.mark.parametrize("api_key,with_authority,error", [(None, True, "credential"), ("key", False, "authority")])
def test_missing_credential_or_authority_fails_before_post(
    tmp_path, api_key, with_authority, error
) -> None:
    database, decision, compiled, contents = _prepared_hosted_run(tmp_path)
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        if request.method == "GET":
            return httpx.Response(404)
        posts += 1
        return httpx.Response(500)

    secret = b"a" * 32
    authority = (
        HostedAuthorityIssuer(secret).issue(
            compiled, datetime.now(UTC) + timedelta(minutes=1)
        )
        if with_authority
        else None
    )
    adapter = HostedProviderAdapter(
        compiled,
        authority=authority,
        gate=HostedAuthorityGate(tmp_path / "authority.sqlite3", secret),
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://fixture.invalid"
        ),
        api_key=api_key,
        content_by_sha256=contents,
    )
    with pytest.raises(HostedExecutionBoundaryError, match=error):
        ProviderExecutionCoordinator(AgentEventStore(database), adapter).run_or_reconcile(
            "hosted-run-001",
            "hosted-execution-001",
            "hosted:idem:001",
            decision,
        )
    assert posts == 0


def test_cost_privacy_and_response_identity_drift_fail_closed(tmp_path) -> None:
    _, _, compiled, contents = _prepared_hosted_run(tmp_path)
    secret = b"d" * 32
    issuer = HostedAuthorityIssuer(secret)
    packet = issuer.issue(compiled, datetime.now(UTC) + timedelta(minutes=1))
    gate = HostedAuthorityGate(tmp_path / "authority.sqlite3", secret)
    with pytest.raises(HostedExecutionBoundaryError, match="privacy"):
        gate.consume(packet.model_copy(update={"privacy_class": "provider_retained"}), compiled)
    with pytest.raises(HostedExecutionBoundaryError, match="cost"):
        gate.consume(packet.model_copy(update={"approved_max_cost_usd": 0.09}), compiled)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "job-drifted",
                "status": "running",
                "metadata": {
                    **compiled.redacted_payload(contents)["metadata"],
                    "route_fingerprint": "f" * 64,
                },
            },
        )

    adapter = HostedProviderAdapter(
        compiled,
        authority=packet,
        gate=gate,
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://fixture.invalid"
        ),
        api_key="fixture",
        content_by_sha256=contents,
    )
    with pytest.raises(HostedExecutionBoundaryError, match="identity"):
        adapter.lookup(compiled.idempotency_key)


@pytest.mark.parametrize(
    "response",
    [httpx.Response(503), httpx.Response(200, json={"id": "missing-fields"})],
)
def test_provider_error_and_malformed_observation_are_bounded(tmp_path, response) -> None:
    _, _, compiled, contents = _prepared_hosted_run(tmp_path)

    def handler(_: httpx.Request) -> httpx.Response:
        return response

    secret = b"e" * 32
    adapter = HostedProviderAdapter(
        compiled,
        authority=None,
        gate=HostedAuthorityGate(tmp_path / "authority.sqlite3", secret),
        client=httpx.Client(
            transport=httpx.MockTransport(handler), base_url="https://fixture.invalid"
        ),
        api_key="fixture",
        content_by_sha256=contents,
    )
    with pytest.raises(HostedExecutionBoundaryError, match="malformed"):
        adapter.lookup(compiled.idempotency_key)
