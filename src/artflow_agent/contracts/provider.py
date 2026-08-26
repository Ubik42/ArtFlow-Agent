from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TaskKind = Literal["scene_direction", "masked_refinement"]
ExecutionKind = Literal["local", "hosted", "mcp"]
PrivacyClass = Literal["local_only", "provider_processed", "provider_retained"]
CostClass = Literal["local_compute", "metered", "subscription"]
ControlKind = Literal[
    "reference_image",
    "mask",
    "depth",
    "world_normal",
    "object_id",
    "multi_turn_edit",
]
EvaluationEvidenceKind = Literal["depth", "world_normal", "object_id", "protected_mask"]


class ProviderModelCapability(BaseModel):
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    tasks: list[TaskKind] = Field(min_length=1)
    controls: list[ControlKind] = Field(default_factory=list)
    max_reference_images: int = Field(default=1, ge=0, le=32)

    @model_validator(mode="after")
    def require_unique_capabilities(self) -> ProviderModelCapability:
        if len(self.tasks) != len(set(self.tasks)):
            raise ValueError("model tasks must be unique")
        if len(self.controls) != len(set(self.controls)):
            raise ValueError("model controls must be unique")
        return self


class ProviderCapabilityManifest(BaseModel):
    schema_id: Literal["provider-capability-manifest/1"] = "provider-capability-manifest/1"
    provider_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    display_name: str = Field(min_length=1)
    execution_kind: ExecutionKind
    privacy_class: PrivacyClass
    cost_class: CostClass
    requires_explicit_cost_approval: bool
    models: list[ProviderModelCapability] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_policy_defaults(self) -> ProviderCapabilityManifest:
        model_ids = [item.model_id for item in self.models]
        if len(model_ids) != len(set(model_ids)):
            raise ValueError("provider model IDs must be unique")
        if self.execution_kind != "local" and not self.requires_explicit_cost_approval:
            raise ValueError("non-local providers require explicit cost approval")
        if self.execution_kind == "local" and self.privacy_class != "local_only":
            raise ValueError("local providers must use local_only privacy")
        return self
