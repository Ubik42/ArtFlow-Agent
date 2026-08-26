from __future__ import annotations

import base64
import binascii
import hashlib
from datetime import UTC, datetime
from typing import Any, Final

import httpx

from .contracts import ProviderExecutionReceipt, ReceiptArtifact
from .hosted_execution import (
    CompiledHostedRequest,
    HostedAuthorityGate,
    HostedAuthorityPacket,
    HostedExecutionBoundaryError,
)
from .provider_execution import (
    ProviderCompletionUnknown,
    ProviderExecutionRequest,
    ProviderObservation,
    ProviderSubmission,
)

OPENAI_IMAGES_PROVIDER_ID: Final = "openai-images"
OPENAI_IMAGES_MODEL_SNAPSHOT: Final = "gpt-image-2-2026-04-21"
OPENAI_IMAGES_EDIT_ENDPOINT: Final = "/v1/images/edits"
_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"


class OpenAIImagesAdapter:
    """Exact, synchronous OpenAI Images edit adapter with no invented lookup API."""

    def __init__(
        self,
        request: CompiledHostedRequest,
        *,
        authority: HostedAuthorityPacket | None,
        gate: HostedAuthorityGate,
        client: httpx.Client,
        api_key: str | None,
        content_by_sha256: dict[str, bytes],
    ) -> None:
        self.request = request
        self.authority = authority
        self.gate = gate
        self.client = client
        self.api_key = api_key
        self.content_by_sha256 = content_by_sha256
        self._observation: ProviderObservation | None = None
        self._output: bytes | None = None

    def submit(self, execution: ProviderExecutionRequest) -> ProviderSubmission:
        self._verify_execution_request(execution)
        api_key = self._require_credential()
        if self.authority is None:
            raise HostedExecutionBoundaryError(
                "OpenAI privacy and cost authority is required"
            )
        image = self._verified_beauty_png()
        prompt = self._bounded_prompt()

        # A transport failure after this point may have executed inference. The packet is
        # deliberately consumed before the first network byte can leave this process.
        self.gate.consume(self.authority, self.request)
        try:
            response = self.client.post(
                OPENAI_IMAGES_EDIT_ENDPOINT,
                headers={"Authorization": f"Bearer {api_key}"},
                data={
                    "model": OPENAI_IMAGES_MODEL_SNAPSHOT,
                    "prompt": prompt,
                    "n": "1",
                    "size": f"{self.request.width}x{self.request.height}",
                    "quality": "medium",
                    "output_format": "png",
                },
                files={"image[]": ("beauty.png", image, "image/png")},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ProviderCompletionUnknown(
                "openai_images_transport_completion_unknown"
            ) from exc

        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise HostedExecutionBoundaryError(
                f"OpenAI Images returned HTTP {response.status_code}"
            ) from exc

        try:
            provider_request_id = response.headers["x-request-id"].strip()
            if not provider_request_id:
                raise ValueError("empty x-request-id")
            body = response.json()
            output = self._decode_single_png(body)
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            # OpenAI already accepted the synchronous request. A malformed response cannot
            # safely be re-submitted, even if no usable artifact reached this process.
            raise ProviderCompletionUnknown(
                "openai_images_response_completion_unknown"
            ) from exc

        now = datetime.now(UTC)
        path = "hosted/openai/result.png"
        receipt = ProviderExecutionReceipt(
            execution_id=self.request.execution_id,
            route_decision_id=self.request.route_decision_id,
            route_fingerprint=self.request.route_fingerprint,
            provider_id=self.request.provider_id,
            model_id=self.request.model_id,
            status="succeeded",
            started_at=now,
            completed_at=now,
            provider_request_id=provider_request_id,
            artifacts=[
                ReceiptArtifact(
                    path=path,
                    sha256=hashlib.sha256(output).hexdigest(),
                    media_type="image/png",
                )
            ],
        )
        self._output = output
        self._observation = ProviderObservation(
            provider_request_id=provider_request_id,
            status="terminal",
            receipt=receipt,
        )
        return ProviderSubmission(provider_request_id=provider_request_id)

    def lookup(self, idempotency_key: str) -> ProviderObservation | None:
        if idempotency_key != self.request.idempotency_key:
            raise HostedExecutionBoundaryError("OpenAI execution identity drifted")
        # The Images API has no documented lookup by client key. Only a complete response
        # observed by this adapter instance is knowable.
        return self._observation

    def fetch_artifact(self, provider_request_id: str, path: str) -> bytes:
        if (
            self._observation is None
            or self._output is None
            or provider_request_id != self._observation.provider_request_id
            or path != "hosted/openai/result.png"
        ):
            raise HostedExecutionBoundaryError("OpenAI output identity drifted")
        return self._output

    def _verify_execution_request(self, execution: ProviderExecutionRequest) -> None:
        decision = execution.route_decision
        if (
            self.request.provider_id != OPENAI_IMAGES_PROVIDER_ID
            or self.request.model_id != OPENAI_IMAGES_MODEL_SNAPSHOT
            or decision.selected.provider_id != OPENAI_IMAGES_PROVIDER_ID
            or decision.selected.model_id != OPENAI_IMAGES_MODEL_SNAPSHOT
            or decision.selected.execution_kind != "hosted"
            or execution.execution_id != self.request.execution_id
            or execution.idempotency_key != self.request.idempotency_key
            or decision.decision_id != self.request.route_decision_id
            or decision.approval_fingerprint() != self.request.route_fingerprint
            or execution.attestation_environment_sha256
            != self.request.attestation_environment_sha256
        ):
            raise HostedExecutionBoundaryError("OpenAI execution identity drifted")
        if self.request.output_count != 1:
            raise HostedExecutionBoundaryError("OpenAI adapter permits exactly one output")

    def _require_credential(self) -> str:
        if not self.api_key:
            raise HostedExecutionBoundaryError("OpenAI credential is missing")
        return self.api_key

    def _verified_beauty_png(self) -> bytes:
        if len(self.request.assets) != 1:
            raise HostedExecutionBoundaryError(
                "OpenAI adapter permits only one beauty input"
            )
        asset = self.request.assets[0]
        if asset.role != "reference_image" or asset.media_type != "image/png":
            raise HostedExecutionBoundaryError(
                "OpenAI adapter requires one reference-image PNG"
            )
        try:
            content = self.content_by_sha256[asset.sha256]
        except KeyError as exc:
            raise HostedExecutionBoundaryError("OpenAI beauty input is missing") from exc
        if hashlib.sha256(content).hexdigest() != asset.sha256:
            raise HostedExecutionBoundaryError("OpenAI beauty input hash mismatched")
        if not content.startswith(_PNG_SIGNATURE):
            raise HostedExecutionBoundaryError("OpenAI beauty input is not a PNG")
        return content

    def _bounded_prompt(self) -> str:
        sections = [f"Goal:\n{self.request.art_goal}"]
        if self.request.preserve:
            sections.append("Preserve:\n- " + "\n- ".join(self.request.preserve))
        if self.request.prohibit:
            sections.append("Do not change:\n- " + "\n- ".join(self.request.prohibit))
        prompt = "\n\n".join(sections)
        if len(prompt) > 8000:
            raise HostedExecutionBoundaryError("OpenAI prompt exceeds adapter limit")
        return prompt

    @staticmethod
    def _decode_single_png(body: Any) -> bytes:
        if not isinstance(body, dict):
            raise TypeError("response is not an object")
        data = body.get("data")
        if not isinstance(data, list) or len(data) != 1:
            raise ValueError("response must contain exactly one output")
        item = data[0]
        if not isinstance(item, dict) or not isinstance(item.get("b64_json"), str):
            raise TypeError("response output omitted base64 PNG")
        output = base64.b64decode(item["b64_json"], validate=True)
        if not output.startswith(_PNG_SIGNATURE):
            raise ValueError("response output is not a PNG")
        return output
