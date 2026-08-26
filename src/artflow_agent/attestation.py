from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, TypeAlias

from pydantic import AwareDatetime, BaseModel, Field

from .contracts import ProviderCapabilityManifest
from .domain import EnvironmentSnapshot, RecipeDefinition


class LocalCapabilityAttestation(BaseModel):
    schema_id: Literal["local-capability-attestation/1"] = "local-capability-attestation/1"
    attestation_id: str
    captured_at: AwareDatetime
    provider_id: str
    model_id: str
    recipe_id: str
    status: Literal["supported", "unsupported", "unknown"]
    reasons: list[str]
    environment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    comfyui_version: str | None
    python_version: str | None
    pytorch_version: str | None
    device_name: str | None
    vram_mb: int | None
    observed_node_count: int = Field(ge=0)
    observed_model_count: int = Field(ge=0)
    required_nodes: list[str]
    required_models: list[str]
    verified_nodes: list[str]
    verified_models: list[str]
    missing_nodes: list[str]
    missing_models: list[str]

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return path

    def verify_fingerprint(self) -> None:
        expected = _environment_sha256(self.model_dump(mode="json"))
        if expected != self.environment_sha256:
            raise ValueError("Local capability attestation fingerprint does not match its facts")

    @classmethod
    def load_verified(cls, path: Path) -> LocalCapabilityAttestation:
        attestation = cls.model_validate_json(path.read_text(encoding="utf-8"))
        attestation.verify_fingerprint()
        return attestation


class HostedCapabilityAttestation(BaseModel):
    """Content-bound observation of a hosted adapter contract, never a live-call claim."""

    schema_id: Literal["hosted-capability-attestation/1"] = (
        "hosted-capability-attestation/1"
    )
    attestation_id: str
    captured_at: AwareDatetime
    provider_id: str
    model_id: str
    status: Literal["supported", "unsupported", "unknown"]
    reasons: list[str]
    environment_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    contract_version: str
    privacy_class: Literal["provider_processed", "provider_retained"]
    max_cost_usd: float = Field(ge=0)
    fixture_only: Literal[True] = True

    def verify_fingerprint(self) -> None:
        expected = _environment_sha256(self.model_dump(mode="json"))
        if expected != self.environment_sha256:
            raise ValueError("Hosted capability attestation fingerprint does not match its facts")


CapabilityAttestation: TypeAlias = LocalCapabilityAttestation | HostedCapabilityAttestation


def attest_hosted_contract_fixture(
    *,
    provider_id: str,
    model_id: str,
    contract_version: str,
    privacy_class: Literal["provider_processed", "provider_retained"],
    max_cost_usd: float,
    fixture_supported: bool,
) -> HostedCapabilityAttestation:
    reasons = [] if fixture_supported else ["hosted_contract_unverified"]
    status: Literal["supported", "unknown"] = "supported" if fixture_supported else "unknown"
    facts = {
        "provider_id": provider_id,
        "model_id": model_id,
        "status": status,
        "reasons": reasons,
        "contract_version": contract_version,
        "privacy_class": privacy_class,
        "max_cost_usd": max_cost_usd,
        "fixture_only": True,
    }
    return HostedCapabilityAttestation(
        attestation_id=f"hosted-attestation-{uuid.uuid4().hex}",
        captured_at=datetime.now(UTC),
        environment_sha256=_environment_sha256(facts),
        **facts,
    )


def attest_local_capability(
    snapshot: EnvironmentSnapshot,
    manifest: ProviderCapabilityManifest,
    model_id: str,
    recipe: RecipeDefinition,
) -> LocalCapabilityAttestation:
    reasons: list[str] = []
    if manifest.execution_kind != "local":
        reasons.append("provider_not_local")
    selected_model = next(
        (model for model in manifest.models if model.model_id == model_id), None
    )
    if selected_model is None:
        reasons.append("model_not_declared")
    else:
        missing_controls = sorted(
            set(recipe.consumed_controls) - set(selected_model.controls)
        )
        reasons.extend(f"control_not_declared:{name}" for name in missing_controls)
    if not recipe.execution_ready:
        reasons.append("recipe_not_execution_ready")

    missing_nodes = sorted(set(recipe.required_nodes) - set(snapshot.nodes))
    missing_models = sorted(set(recipe.required_models) - set(snapshot.models))
    verified_nodes = sorted(set(recipe.required_nodes) & set(snapshot.nodes))
    verified_models = sorted(set(recipe.required_models) & set(snapshot.models))
    if snapshot.reachable:
        reasons.extend(f"missing_node:{name}" for name in missing_nodes)
        reasons.extend(f"missing_model:{name}" for name in missing_models)
        if (
            recipe.estimated_vram_mb is not None
            and snapshot.vram_mb is not None
            and snapshot.vram_mb < recipe.estimated_vram_mb
        ):
            reasons.append("insufficient_vram")
    else:
        reasons.append("runtime_unreachable")

    unknown = not snapshot.reachable or snapshot.vram_mb is None
    status: Literal["supported", "unsupported", "unknown"]
    hard_failures = [reason for reason in reasons if reason != "runtime_unreachable"]
    if hard_failures:
        status = "unsupported"
    elif unknown:
        status = "unknown"
    else:
        status = "supported"

    facts = {
        "provider_id": manifest.provider_id,
        "model_id": model_id,
        "recipe_id": recipe.recipe_id,
        "status": status,
        "reasons": reasons,
        "comfyui_version": snapshot.comfyui_version,
        "python_version": snapshot.python_version,
        "pytorch_version": snapshot.pytorch_version,
        "device_name": snapshot.device_name,
        "vram_mb": snapshot.vram_mb,
        "observed_node_count": len(snapshot.nodes),
        "observed_model_count": len(snapshot.models),
        "required_nodes": sorted(recipe.required_nodes),
        "required_models": sorted(recipe.required_models),
        "verified_nodes": verified_nodes,
        "verified_models": verified_models,
        "missing_nodes": missing_nodes,
        "missing_models": missing_models,
    }
    return LocalCapabilityAttestation(
        attestation_id=f"attestation-{uuid.uuid4().hex}",
        captured_at=datetime.now(UTC),
        environment_sha256=_environment_sha256(facts),
        **facts,
    )


def _environment_sha256(value: dict[str, object]) -> str:
    excluded = {"schema_id", "attestation_id", "captured_at", "environment_sha256"}
    facts = {key: item for key, item in value.items() if key not in excluded}
    canonical = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
