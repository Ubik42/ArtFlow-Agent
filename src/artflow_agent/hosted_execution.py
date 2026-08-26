from __future__ import annotations

import base64
import hashlib
import hmac
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Literal
from urllib.parse import quote

import httpx
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .agent_runtime import AgentEventStore
from .contracts import ProviderExecutionReceipt, ReceiptArtifact
from .contracts.provider import PrivacyClass
from .provider_execution import (
    ProviderExecutionRequest,
    ProviderObservation,
    ProviderSubmission,
)


class HostedExecutionBoundaryError(RuntimeError):
    """Raised when hosted execution is not explicitly authorized or cannot be verified."""


class HostedAssetReference(BaseModel):
    role: Literal["reference_image", "depth", "world_normal", "object_id", "mask"]
    package_path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: Literal["image/png", "image/x-exr"]

    @model_validator(mode="after")
    def require_package_relative_path(self) -> HostedAssetReference:
        path = PurePosixPath(self.package_path.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Hosted asset path must remain package-relative")
        return self


class CompiledHostedRequest(BaseModel):
    schema_id: Literal["compiled-hosted-request/1"] = "compiled-hosted-request/1"
    run_id: str
    execution_id: str
    idempotency_key: str
    route_decision_id: str
    route_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_id: str
    model_id: str
    scene_package_id: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    attestation_environment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    privacy_class: Literal["provider_processed", "provider_retained"]
    approved_max_cost_usd: float = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    width: int = Field(ge=64, le=16384)
    height: int = Field(ge=64, le=16384)
    output_count: int = Field(ge=1, le=8)
    art_goal: str = Field(min_length=1, max_length=4000)
    preserve: list[str] = Field(max_length=64)
    prohibit: list[str] = Field(max_length=64)
    assets: list[HostedAssetReference] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def enforce_cost_and_asset_allowlist(self) -> CompiledHostedRequest:
        if self.estimated_cost_usd > self.approved_max_cost_usd:
            raise ValueError("Hosted estimated cost exceeds approved maximum")
        roles = [item.role for item in self.assets]
        if len(roles) != len(set(roles)):
            raise ValueError("Hosted request asset roles must be unique")
        if "reference_image" not in roles:
            raise ValueError("Hosted request requires a reference image")
        return self

    def authority_binding(self) -> str:
        return _canonical_sha256(self.model_dump(mode="json"))

    def redacted_payload(self, content_by_sha256: dict[str, bytes]) -> dict[str, Any]:
        assets = []
        for item in self.assets:
            try:
                content = content_by_sha256[item.sha256]
            except KeyError as exc:
                raise HostedExecutionBoundaryError(
                    f"Missing allowlisted hosted asset: {item.role}"
                ) from exc
            if hashlib.sha256(content).hexdigest() != item.sha256:
                raise HostedExecutionBoundaryError(
                    f"Hosted asset hash mismatch: {item.role}"
                )
            assets.append(
                {
                    "role": item.role,
                    "sha256": item.sha256,
                    "media_type": item.media_type,
                    "content_base64": base64.b64encode(content).decode("ascii"),
                }
            )
        return {
            "model": self.model_id,
            "prompt": self.art_goal,
            "preserve": self.preserve,
            "prohibit": self.prohibit,
            "width": self.width,
            "height": self.height,
            "output_count": self.output_count,
            "assets": assets,
            "metadata": {
                "execution_id": self.execution_id,
                "route_decision_id": self.route_decision_id,
                "route_fingerprint": self.route_fingerprint,
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "privacy_class": self.privacy_class,
            },
        }


class HostedRequestCompiler:
    """Builds a remote-safe allowlist from authoritative run state."""

    _PASS_ROLES: ClassVar[dict[str, str]] = {
        "beauty": "reference_image",
        "depth": "depth",
        "world_normal": "world_normal",
        "object_id": "object_id",
        "editable_mask": "mask",
    }

    def __init__(self, store: AgentEventStore) -> None:
        self.store = store

    def compile(
        self,
        run_id: str,
        execution_id: str,
        *,
        estimated_cost_usd: float,
    ) -> CompiledHostedRequest:
        state = self.store.load(run_id)
        if state.scene is None or state.route_decision is None:
            raise HostedExecutionBoundaryError("Hosted execution context is incomplete")
        decision = state.route_decision
        if decision.selected.execution_kind != "hosted":
            raise HostedExecutionBoundaryError("Approved route is not hosted")
        if decision.selected.privacy_class == "local_only":
            raise HostedExecutionBoundaryError("Hosted route cannot claim local-only privacy")
        execution = next(
            (item for item in state.provider_executions if item.execution_id == execution_id),
            None,
        )
        if execution is None or execution.status != "reserved":
            raise HostedExecutionBoundaryError("Hosted execution must be durably reserved first")
        if execution.route_fingerprint != decision.approval_fingerprint():
            raise HostedExecutionBoundaryError("Hosted route approval is stale")
        attestation = next(
            (
                item
                for item in state.capability_attestations
                if item.environment_sha256 == execution.attestation_environment_sha256
            ),
            None,
        )
        if attestation is None or attestation.schema_id != "hosted-capability-attestation/1":
            raise HostedExecutionBoundaryError("Matching hosted attestation is missing")
        if attestation.status != "supported":
            raise HostedExecutionBoundaryError("Hosted adapter contract is not supported")
        if attestation.privacy_class != decision.selected.privacy_class:
            raise HostedExecutionBoundaryError("Hosted privacy class drifted after approval")
        if attestation.max_cost_usd < decision.max_cost_usd:
            raise HostedExecutionBoundaryError("Hosted capability cost ceiling is stale")
        artifacts = {item.path: item for item in state.scene.artifacts}
        assets: list[HostedAssetReference] = []
        for scene_pass in state.scene.package.passes:
            role = self._PASS_ROLES.get(scene_pass.kind)
            if role is None or role not in decision.execution_intent.required_controls:
                continue
            verified = artifacts.get(scene_pass.artifact.path)
            if verified is None or verified.sha256 != scene_pass.artifact.sha256:
                raise HostedExecutionBoundaryError("Hosted input is not a verified package artifact")
            assets.append(
                HostedAssetReference(
                    role=role,
                    package_path=verified.path,
                    sha256=verified.sha256,
                    media_type=scene_pass.artifact.media_type,
                )
            )
        return CompiledHostedRequest(
            run_id=run_id,
            execution_id=execution_id,
            idempotency_key=execution.idempotency_key,
            route_decision_id=decision.decision_id,
            route_fingerprint=decision.approval_fingerprint(),
            provider_id=decision.selected.provider_id,
            model_id=decision.selected.model_id,
            scene_package_id=state.scene.package.package_id,
            scene_package_sha256=state.scene.archive_sha256,
            attestation_environment_sha256=execution.attestation_environment_sha256,
            privacy_class=decision.selected.privacy_class,
            approved_max_cost_usd=decision.max_cost_usd,
            estimated_cost_usd=estimated_cost_usd,
            width=decision.execution_intent.width,
            height=decision.execution_intent.height,
            output_count=decision.execution_intent.output_count,
            art_goal=state.scene.package.art_intent.goal,
            preserve=state.scene.package.art_intent.preserve,
            prohibit=state.scene.package.art_intent.prohibit,
            assets=assets,
        )


class HostedAuthorityPacket(BaseModel):
    packet_id: str
    binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    privacy_class: Literal["provider_processed", "provider_retained"]
    approved_max_cost_usd: float = Field(ge=0)
    expires_at: AwareDatetime
    signature: str = Field(pattern=r"^[a-f0-9]{64}$")


class HostedAuthorityIssuer:
    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("Hosted authority secret must contain at least 32 bytes")
        self._secret = secret

    def issue(
        self, request: CompiledHostedRequest, expires_at: datetime
    ) -> HostedAuthorityPacket:
        packet_id = f"hosted-authority-{uuid.uuid4().hex}"
        fields = (
            packet_id,
            request.authority_binding(),
            request.privacy_class,
            request.approved_max_cost_usd,
            expires_at,
        )
        return HostedAuthorityPacket(
            packet_id=packet_id,
            binding_sha256=fields[1],
            privacy_class=fields[2],
            approved_max_cost_usd=fields[3],
            expires_at=expires_at,
            signature=_authority_signature(self._secret, *fields),
        )


class HostedAuthorityGate:
    def __init__(self, database: Path, secret: bytes) -> None:
        self.database = database
        self._secret = secret
        database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS consumed_hosted_authority "
                "(packet_id TEXT PRIMARY KEY, consumed_at TEXT NOT NULL)"
            )

    def verify(
        self, packet: HostedAuthorityPacket, request: CompiledHostedRequest
    ) -> None:
        if packet.binding_sha256 != request.authority_binding():
            raise HostedExecutionBoundaryError("Hosted authority is stale")
        if packet.privacy_class != request.privacy_class:
            raise HostedExecutionBoundaryError("Hosted privacy authority drifted")
        if packet.approved_max_cost_usd != request.approved_max_cost_usd:
            raise HostedExecutionBoundaryError("Hosted cost authority drifted")
        if datetime.now(UTC) >= packet.expires_at:
            raise HostedExecutionBoundaryError("Hosted authority expired")
        expected = _authority_signature(
            self._secret,
            packet.packet_id,
            packet.binding_sha256,
            packet.privacy_class,
            packet.approved_max_cost_usd,
            packet.expires_at,
        )
        if not hmac.compare_digest(expected, packet.signature):
            raise HostedExecutionBoundaryError("Hosted authority signature is invalid")
        with sqlite3.connect(self.database) as connection:
            consumed = connection.execute(
                "SELECT 1 FROM consumed_hosted_authority WHERE packet_id = ?",
                (packet.packet_id,),
            ).fetchone()
        if consumed is not None:
            raise HostedExecutionBoundaryError("Hosted authority was already consumed")

    def consume(
        self, packet: HostedAuthorityPacket, request: CompiledHostedRequest
    ) -> None:
        self.verify(packet, request)
        try:
            with sqlite3.connect(self.database) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO consumed_hosted_authority VALUES (?, ?)",
                    (packet.packet_id, datetime.now(UTC).isoformat()),
                )
        except sqlite3.IntegrityError as exc:
            raise HostedExecutionBoundaryError("Hosted authority was already consumed") from exc


class HostedProviderAdapter:
    """Recorded-contract hosted provider implementing the durable execution port."""

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

    def submit(self, execution: ProviderExecutionRequest) -> ProviderSubmission:
        self._verify_execution_request(execution)
        headers = self._auth_headers()
        if self.authority is None:
            raise HostedExecutionBoundaryError("Hosted privacy and cost authority is required")
        payload = self.request.redacted_payload(self.content_by_sha256)
        self.gate.consume(self.authority, self.request)
        try:
            response = self.client.post(
                "/v1/image-edits",
                json=payload,
                headers={
                    **headers,
                    "Idempotency-Key": execution.idempotency_key,
                },
            )
            response.raise_for_status()
            body = response.json()
            request_id = body["id"]
            if not isinstance(request_id, str) or not request_id:
                raise ValueError("missing request ID")
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise HostedExecutionBoundaryError(
                f"Hosted provider rejected submission: {exc}"
            ) from exc
        return ProviderSubmission(provider_request_id=request_id)

    def lookup(self, idempotency_key: str) -> ProviderObservation | None:
        if idempotency_key != self.request.idempotency_key:
            raise HostedExecutionBoundaryError("Hosted lookup idempotency key drifted")
        headers = self._auth_headers()
        try:
            response = self.client.get(
                f"/v1/image-edits/by-idempotency/{quote(idempotency_key, safe='')}",
                headers=headers,
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            body = response.json()
            return self._normalize_observation(body)
        except HostedExecutionBoundaryError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise HostedExecutionBoundaryError(
                f"Hosted provider observation is malformed: {exc}"
            ) from exc

    def fetch_artifact(self, provider_request_id: str, path: str) -> bytes:
        prefix = f"hosted/{provider_request_id}/"
        if not path.startswith(prefix) or "/" in path[len(prefix) :]:
            raise HostedExecutionBoundaryError("Hosted receipt artifact path is invalid")
        filename = path[len(prefix) :]
        headers = self._auth_headers()
        try:
            response = self.client.get(
                f"/v1/image-edits/{quote(provider_request_id, safe='')}/outputs/"
                f"{quote(filename, safe='')}",
                headers=headers,
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            raise HostedExecutionBoundaryError(
                f"Hosted artifact download failed: {exc}"
            ) from exc

    def _verify_execution_request(self, execution: ProviderExecutionRequest) -> None:
        decision = execution.route_decision
        if (
            execution.execution_id != self.request.execution_id
            or execution.idempotency_key != self.request.idempotency_key
            or decision.decision_id != self.request.route_decision_id
            or decision.approval_fingerprint() != self.request.route_fingerprint
            or execution.attestation_environment_sha256
            != self.request.attestation_environment_sha256
        ):
            raise HostedExecutionBoundaryError("Hosted execution request identity drifted")

    def _auth_headers(self) -> dict[str, str]:
        if not self.api_key:
            raise HostedExecutionBoundaryError("Hosted provider credential is missing")
        return {"Authorization": f"Bearer {self.api_key}"}

    def _normalize_observation(self, body: dict[str, Any]) -> ProviderObservation:
        request_id = body["id"]
        status = body["status"]
        metadata = body["metadata"]
        expected_metadata = {
            "execution_id": self.request.execution_id,
            "route_decision_id": self.request.route_decision_id,
            "route_fingerprint": self.request.route_fingerprint,
            "provider_id": self.request.provider_id,
            "model_id": self.request.model_id,
            "privacy_class": self.request.privacy_class,
        }
        if any(metadata.get(key) != value for key, value in expected_metadata.items()):
            raise HostedExecutionBoundaryError("Hosted response identity or privacy drifted")
        actual_cost = float(body.get("cost_usd", 0))
        if actual_cost > self.request.approved_max_cost_usd:
            raise HostedExecutionBoundaryError("Hosted provider reported cost above approval")
        if status in {"queued", "running"}:
            return ProviderObservation(provider_request_id=request_id, status="running")
        now = datetime.now(UTC)
        if status in {"failed", "cancelled"}:
            receipt = ProviderExecutionReceipt(
                execution_id=self.request.execution_id,
                route_decision_id=self.request.route_decision_id,
                route_fingerprint=self.request.route_fingerprint,
                provider_id=self.request.provider_id,
                model_id=self.request.model_id,
                status=status,
                started_at=now,
                completed_at=now,
                provider_request_id=request_id,
                error_code=str(body.get("error_code") or "hosted_provider_failure"),
            )
            return ProviderObservation(
                provider_request_id=request_id, status="terminal", receipt=receipt
            )
        if status != "succeeded":
            raise HostedExecutionBoundaryError("Hosted response has unknown status")
        outputs = body["outputs"]
        artifacts = [
            ReceiptArtifact(
                path=f"hosted/{request_id}/{item['filename']}",
                sha256=item["sha256"],
                media_type=item.get("media_type", "image/png"),
            )
            for item in outputs
        ]
        receipt = ProviderExecutionReceipt(
            execution_id=self.request.execution_id,
            route_decision_id=self.request.route_decision_id,
            route_fingerprint=self.request.route_fingerprint,
            provider_id=self.request.provider_id,
            model_id=self.request.model_id,
            status="succeeded",
            started_at=now,
            completed_at=now,
            provider_request_id=request_id,
            artifacts=artifacts,
        )
        return ProviderObservation(
            provider_request_id=request_id, status="terminal", receipt=receipt
        )


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _authority_signature(
    secret: bytes,
    packet_id: str,
    binding_sha256: str,
    privacy_class: PrivacyClass,
    approved_max_cost_usd: float,
    expires_at: datetime,
) -> str:
    payload = (
        f"{packet_id}\n{binding_sha256}\n{privacy_class}\n"
        f"{approved_max_cost_usd:.12g}\n{expires_at.isoformat()}"
    ).encode()
    return hmac.new(secret, payload, hashlib.sha256).hexdigest()
