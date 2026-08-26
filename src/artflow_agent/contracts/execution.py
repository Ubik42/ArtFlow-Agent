from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .provider import (
    ControlKind,
    CostClass,
    EvaluationEvidenceKind,
    ExecutionKind,
    PrivacyClass,
    TaskKind,
)


class ProviderSelection(BaseModel):
    provider_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    model_id: str = Field(min_length=1)
    execution_kind: ExecutionKind
    privacy_class: PrivacyClass
    cost_class: CostClass


class RejectedProviderAlternative(ProviderSelection):
    reasons: list[str] = Field(min_length=1)


class RouteExecutionIntent(BaseModel):
    # Provider-consumed inputs only. Auxiliary scene passes belong in evaluation_evidence.
    required_controls: list[ControlKind] = Field(min_length=1)
    evaluation_evidence: list[EvaluationEvidenceKind] = Field(default_factory=list)
    output_count: int = Field(default=1, ge=1, le=8)
    width: int = Field(ge=64, le=16384)
    height: int = Field(ge=64, le=16384)
    delivery_format: Literal["png", "exr", "tiff"]
    intent_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def require_unique_controls(self) -> RouteExecutionIntent:
        if len(self.required_controls) != len(set(self.required_controls)):
            raise ValueError("required route controls must be unique")
        if len(self.evaluation_evidence) != len(set(self.evaluation_evidence)):
            raise ValueError("route evaluation evidence must be unique")
        return self


class RouteDecision(BaseModel):
    """Auditable provider choice whose policy-sensitive fields share one integrity fingerprint."""

    schema_id: Literal["route-decision/1"] = "route-decision/1"
    decision_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    scene_package_id: str = Field(min_length=1)
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    task: TaskKind
    selected: ProviderSelection
    rejected: list[RejectedProviderAlternative] = Field(default_factory=list)
    execution_intent: RouteExecutionIntent
    privacy_ceiling: PrivacyClass
    max_cost_usd: float = Field(ge=0)
    requires_explicit_approval: bool
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def enforce_route_policy(self) -> RouteDecision:
        if self.selected.execution_kind == "local" and self.selected.privacy_class != "local_only":
            raise ValueError("local routes must use local_only privacy")
        if self.selected.execution_kind != "local" and not self.requires_explicit_approval:
            raise ValueError("non-local routes require explicit approval")
        if self.selected.cost_class != "local_compute" and not self.requires_explicit_approval:
            raise ValueError("metered or subscription routes require explicit approval")
        selected_key = (self.selected.provider_id, self.selected.model_id)
        rejected_keys = [(item.provider_id, item.model_id) for item in self.rejected]
        if selected_key in rejected_keys:
            raise ValueError("selected provider cannot also be rejected")
        if len(rejected_keys) != len(set(rejected_keys)):
            raise ValueError("rejected provider alternatives must be unique")
        return self

    def approval_fingerprint(self) -> str:
        """Bind policy and execution to every cost, privacy, capability and input field."""

        payload = {
            "decision_id": self.decision_id,
            "scene_package_id": self.scene_package_id,
            "scene_package_sha256": self.scene_package_sha256,
            "task": self.task,
            "selected": self.selected.model_dump(mode="json"),
            "execution_intent": self.execution_intent.model_dump(mode="json"),
            "privacy_ceiling": self.privacy_ceiling,
            "max_cost_usd": self.max_cost_usd,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()


class ApprovalGrant(BaseModel):
    schema_id: Literal["approval-grant/1"] = "approval-grant/1"
    approval_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    route_decision_id: str = Field(min_length=1)
    route_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_by: str = Field(min_length=1)
    approved_at: AwareDatetime
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_expiry(self) -> ApprovalGrant:
        if self.expires_at is not None and self.expires_at <= self.approved_at:
            raise ValueError("approval expiry must be after approval time")
        return self

    def authorizes(self, decision: RouteDecision, *, at: datetime | None = None) -> bool:
        if self.route_decision_id != decision.decision_id:
            return False
        if self.route_fingerprint != decision.approval_fingerprint():
            return False
        instant = at or datetime.now(UTC)
        return self.expires_at is None or instant < self.expires_at


class ReceiptArtifact(BaseModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_portable_path(self) -> ReceiptArtifact:
        normalized = self.path.replace("\\", "/")
        if normalized.startswith("/") or ":" in normalized.split("/", 1)[0]:
            raise ValueError("receipt artifact path must be package-relative")
        if ".." in normalized.split("/"):
            raise ValueError("receipt artifact path must not escape its package")
        return self


class ProviderExecutionReceipt(BaseModel):
    schema_id: Literal["provider-execution-receipt/1"] = "provider-execution-receipt/1"
    execution_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    route_decision_id: str = Field(min_length=1)
    route_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    status: Literal["succeeded", "failed", "cancelled"]
    started_at: AwareDatetime
    completed_at: AwareDatetime
    provider_request_id: str | None = None
    artifacts: list[ReceiptArtifact] = Field(default_factory=list)
    error_code: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> ProviderExecutionReceipt:
        if self.completed_at < self.started_at:
            raise ValueError("receipt completion cannot precede start")
        if self.status == "succeeded" and not self.artifacts:
            raise ValueError("successful execution requires at least one artifact")
        if self.status != "succeeded" and not self.error_code:
            raise ValueError("failed or cancelled execution requires an error code")
        return self
