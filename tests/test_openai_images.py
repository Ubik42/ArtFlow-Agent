import base64
import hashlib
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from artflow_agent.contracts import RouteDecision
from artflow_agent.hosted_execution import (
    CompiledHostedRequest,
    HostedAssetReference,
    HostedAuthorityGate,
    HostedAuthorityIssuer,
    HostedExecutionBoundaryError,
)
from artflow_agent.openai_images import OpenAIImagesAdapter
from artflow_agent.provider_execution import (
    ProviderCompletionUnknown,
    ProviderExecutionRequest,
)

PNG = b"\x89PNG\r\n\x1a\nfixture-png"


def _decision() -> RouteDecision:
    return RouteDecision(
        decision_id="route-openai-001",
        scene_package_id="scene-fixture",
        scene_package_sha256="a" * 64,
        task="scene_direction",
        selected={
            "provider_id": "openai-images",
            "model_id": "gpt-image-2-2026-04-21",
            "execution_kind": "hosted",
            "privacy_class": "provider_retained",
            "cost_class": "metered",
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
        privacy_ceiling="provider_retained",
        max_cost_usd=0.25,
        requires_explicit_approval=True,
        rationale="One explicitly approved synchronous portfolio comparison.",
    )


def _compiled(
    decision: RouteDecision, *, assets: list[HostedAssetReference] | None = None
) -> CompiledHostedRequest:
    digest = hashlib.sha256(PNG).hexdigest()
    return CompiledHostedRequest(
        run_id="run-openai-001",
        execution_id="execution-openai-001",
        idempotency_key="openai:execution:001",
        route_decision_id=decision.decision_id,
        route_fingerprint=decision.approval_fingerprint(),
        provider_id=decision.selected.provider_id,
        model_id=decision.selected.model_id,
        scene_package_id=decision.scene_package_id,
        scene_package_sha256=decision.scene_package_sha256,
        attestation_environment_sha256="c" * 64,
        privacy_class="provider_retained",
        approved_max_cost_usd=0.25,
        estimated_cost_usd=0.10,
        width=1280,
        height=720,
        output_count=1,
        art_goal="Create a cinematic but composition-preserving material direction.",
        preserve=["camera", "silhouette"],
        prohibit=["new objects"],
        assets=assets
        or [
            HostedAssetReference(
                role="reference_image",
                package_path="passes/beauty.png",
                sha256=digest,
                media_type="image/png",
            )
        ],
    )


def _execution(decision: RouteDecision) -> ProviderExecutionRequest:
    return ProviderExecutionRequest(
        execution_id="execution-openai-001",
        idempotency_key="openai:execution:001",
        route_decision=decision,
        attestation_environment_sha256="c" * 64,
    )


def _adapter(tmp_path, compiled, handler, *, api_key="test-key", authority=True):
    secret = b"o" * 32
    packet = (
        HostedAuthorityIssuer(secret).issue(
            compiled, datetime.now(UTC) + timedelta(minutes=5)
        )
        if authority
        else None
    )
    digest = hashlib.sha256(PNG).hexdigest()
    return OpenAIImagesAdapter(
        compiled,
        authority=packet,
        gate=HostedAuthorityGate(tmp_path / "openai-authority.sqlite3", secret),
        client=httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://api.openai.com",
        ),
        api_key=api_key,
        content_by_sha256={digest: PNG},
    )


def test_exact_multipart_mapping_and_provenance_bytes_are_preserved(tmp_path) -> None:
    decision = _decision()
    compiled = _compiled(decision)
    output = b"\x89PNG\r\n\x1a\nC2PA-and-SynthID-bytes"
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["headers"] = dict(request.headers)
        observed["body"] = request.read()
        return httpx.Response(
            200,
            headers={"x-request-id": "req-openai-fixture-001"},
            json={"data": [{"b64_json": base64.b64encode(output).decode()}]},
        )

    adapter = _adapter(tmp_path, compiled, handler)
    submission = adapter.submit(_execution(decision))
    observation = adapter.lookup("openai:execution:001")

    assert submission.provider_request_id == "req-openai-fixture-001"
    assert observation is not None and observation.receipt is not None
    artifact = observation.receipt.artifacts[0]
    assert artifact.sha256 == hashlib.sha256(output).hexdigest()
    assert adapter.fetch_artifact(submission.provider_request_id, artifact.path) == output
    assert "idempotency-key" not in observed["headers"]
    body = observed["body"]
    assert body.count(b'name="image[]"') == 1
    assert b"beauty.png" in body
    assert b"gpt-image-2-2026-04-21" in body
    assert b"1280x720" in body
    assert b"world_normal" not in body and b"object_id" not in body

    with pytest.raises(HostedExecutionBoundaryError, match="already consumed"):
        adapter.submit(_execution(decision))


@pytest.mark.parametrize(
    "api_key,authority,error",
    [(None, True, "credential"), ("test-key", False, "authority")],
)
def test_missing_credential_or_authority_fails_before_network(
    tmp_path, api_key, authority, error
) -> None:
    decision = _decision()
    compiled = _compiled(decision)
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    adapter = _adapter(
        tmp_path, compiled, handler, api_key=api_key, authority=authority
    )
    with pytest.raises(HostedExecutionBoundaryError, match=error):
        adapter.submit(_execution(decision))
    assert calls == 0


def test_auxiliary_pass_upload_is_rejected_before_network(tmp_path) -> None:
    decision = _decision()
    digest = hashlib.sha256(PNG).hexdigest()
    compiled = _compiled(
        decision,
        assets=[
            HostedAssetReference(
                role="reference_image",
                package_path="passes/beauty.png",
                sha256=digest,
                media_type="image/png",
            ),
            HostedAssetReference(
                role="depth",
                package_path="passes/depth.exr",
                sha256=digest,
                media_type="image/x-exr",
            ),
        ],
    )
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    with pytest.raises(HostedExecutionBoundaryError, match="only one beauty"):
        _adapter(tmp_path, compiled, handler).submit(_execution(decision))
    assert calls == 0


@pytest.mark.parametrize(
    "response",
    [
        {"data": [{"b64_json": "not-base64"}]},
        {"data": [{"b64_json": "a"}, {"b64_json": "b"}]},
    ],
)
def test_malformed_or_multiple_outputs_become_non_retriable_unknown(
    tmp_path, response
) -> None:
    decision = _decision()
    compiled = _compiled(decision)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"x-request-id": "req-malformed"}, json=response
        )

    adapter = _adapter(tmp_path, compiled, handler)
    with pytest.raises(ProviderCompletionUnknown, match="response_completion_unknown"):
        adapter.submit(_execution(decision))
    with pytest.raises(HostedExecutionBoundaryError, match="already consumed"):
        adapter.submit(_execution(decision))


def test_ambiguous_transport_and_provider_error_fail_closed(tmp_path) -> None:
    decision = _decision()
    compiled = _compiled(decision)

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("response lost", request=request)

    with pytest.raises(ProviderCompletionUnknown, match="transport_completion_unknown"):
        _adapter(tmp_path / "timeout", compiled, timeout_handler).submit(
            _execution(decision)
        )

    def error_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    with pytest.raises(HostedExecutionBoundaryError, match="HTTP 429"):
        _adapter(tmp_path / "provider", compiled, error_handler).submit(
            _execution(decision)
        )


def test_execution_identity_drift_fails_before_network(tmp_path) -> None:
    decision = _decision()
    compiled = _compiled(decision)
    drifted = decision.model_copy(
        update={"selected": decision.selected.model_copy(update={"model_id": "drifted"})}
    )
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    with pytest.raises(HostedExecutionBoundaryError, match="identity drifted"):
        _adapter(tmp_path, compiled, handler).submit(_execution(drifted))
    assert calls == 0
