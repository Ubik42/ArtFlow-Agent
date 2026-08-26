from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator


class LiveRunAction(BaseModel):
    action_id: str
    target: Literal["comfy-local", "openai-images", "unreal"]
    operation: str
    external_side_effect: bool
    authorized: Literal[False] = False


class ProviderRecoveryFacts(BaseModel):
    client_idempotency_key: Literal["not_documented"]
    lookup_by_client_key: Literal["not_available"]
    synchronous_response: bool
    ambiguous_completion_policy: Literal["do_not_retry_escalate"]


class LiveRunAuthorizationDossier(BaseModel):
    schema_id: Literal["live-run-authorization-dossier/1"] = (
        "live-run-authorization-dossier/1"
    )
    dossier_id: str
    authorization_state: Literal["awaiting_user"] = "awaiting_user"
    scene_evidence_level: Literal["fixture"]
    scene_package_id: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    local_provider_id: Literal["comfy-local"]
    local_recipe_id: str
    local_attestation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    hosted_provider_id: Literal["openai-images"]
    hosted_model_snapshot: Literal["gpt-image-2-2026-04-21"]
    hosted_endpoint: Literal["/v1/images/edits"]
    hosted_privacy_class: Literal["provider_retained"]
    credential_environment_variable: Literal["OPENAI_API_KEY"]
    credential_status: Literal["not_inspected"]
    allowed_hosted_passes: list[Literal["beauty"]] = Field(min_length=1, max_length=1)
    local_only_evaluation_passes: list[
        Literal["depth", "world_normal", "object_id"]
    ] = Field(min_length=3, max_length=3)
    output_count: Literal[1]
    output_size: Literal["1280x720"]
    output_quality: Literal["medium"]
    output_format: Literal["png"]
    maximum_approved_cost_usd: float = Field(gt=0, le=1)
    cost_is_provider_enforced: Literal[False]
    recovery: ProviderRecoveryFacts
    actions: list[LiveRunAction] = Field(min_length=3)
    unresolved_requirements: list[str] = Field(min_length=1)
    official_sources: list[HttpUrl] = Field(min_length=4)

    @model_validator(mode="after")
    def enforce_unexecuted_dossier(self) -> LiveRunAuthorizationDossier:
        if any(action.authorized for action in self.actions):
            raise ValueError("Dossier cannot authorize its own actions")
        if len(self.allowed_hosted_passes) != len(set(self.allowed_hosted_passes)):
            raise ValueError("Hosted pass allowlist must be unique")
        if set(self.local_only_evaluation_passes) != {
            "depth",
            "world_normal",
            "object_id",
        }:
            raise ValueError("Auxiliary scene passes must remain local-only")
        return self

    @classmethod
    def load(cls, path: Path) -> LiveRunAuthorizationDossier:
        if not path.is_file():
            raise FileNotFoundError(path)
        dossier = cls.model_validate_json(path.read_text(encoding="utf-8"))
        for action in dossier.actions:
            if PurePosixPath(action.operation).is_absolute():
                raise ValueError("Dossier operations must be descriptions, not host paths")
        return dossier
