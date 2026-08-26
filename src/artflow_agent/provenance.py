from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: BaseModel | dict[str, Any], hash_field: str) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else dict(value)
    payload.pop(hash_field, None)
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class EvidenceBinding(BaseModel):
    role: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,79}$")
    path: str = Field(min_length=1, max_length=500)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str = Field(min_length=3, max_length=100)


class UnrealReturnRequest(BaseModel):
    schema_id: Literal["artflow-unreal-return-request/1"] = (
        "artflow-unreal-return-request/1"
    )
    import_id: str = Field(pattern=r"^return-[a-f0-9]{20}$")
    run_id: str
    source: EvidenceBinding
    destination_asset_path: str = Field(pattern=r"^/Game/ArtFlow/Returns/[A-Za-z0-9_]+$")
    destination_scene_path: Literal["/Game/ArtFlowDemo"] = "/Game/ArtFlowDemo"
    source_scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    adoption_decision_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    tribunal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    multimodal_tribunal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bounded_revision_request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bounded_revision_result_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    operation: Literal["import_art_direction_texture_and_bind_scene"] = (
        "import_art_direction_texture_and_bind_scene"
    )
    authority_scope: Literal["project_local_unreal_fixture"] = (
        "project_local_unreal_fixture"
    )
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    def expected_sha256(self) -> str:
        return canonical_sha256(self, "request_sha256")

    @model_validator(mode="after")
    def validate_hash(self) -> UnrealReturnRequest:
        if self.request_sha256 != self.expected_sha256():
            raise ValueError("Unreal return request hash mismatch")
        return self


class UnrealReturnReceipt(BaseModel):
    schema_id: Literal["artflow-unreal-return-receipt/1"] = (
        "artflow-unreal-return-receipt/1"
    )
    import_id: str
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["imported"]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    imported_asset_path: str
    bound_scene_path: str
    binding_actor_label: str
    engine_version: str
    metadata: dict[str, str]
    completed_at: str
    receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    def expected_sha256(self) -> str:
        return canonical_sha256(self, "receipt_sha256")

    @model_validator(mode="after")
    def validate_hash(self) -> UnrealReturnReceipt:
        if self.receipt_sha256 != self.expected_sha256():
            raise ValueError("Unreal return receipt hash mismatch")
        return self


class ProvenanceVerification(BaseModel):
    schema_id: Literal["artflow-provenance-verification/1"] = (
        "artflow-provenance-verification/1"
    )
    status: Literal["passed_with_declared_limitations", "failed"]
    hash_chain_valid: bool
    c2pa_signature_status: Literal["not_present", "verified"]
    verified_bindings: int = Field(ge=0)
    total_bindings: int = Field(ge=0)
    checks: list[str]
    failures: list[str]
    limitations: list[str]


class ProvenanceManifest(BaseModel):
    schema_id: Literal["artflow-c2pa-compatible-provenance/1"] = (
        "artflow-c2pa-compatible-provenance/1"
    )
    c2pa_reference_version: Literal["2.4.0"] = "2.4.0"
    conformance: Literal["compatible_unsigned_sidecar"] = "compatible_unsigned_sidecar"
    claim_generator_info: dict[str, str]
    instance_id: str
    title: str
    output: EvidenceBinding
    ingredients: list[EvidenceBinding]
    assertions: dict[str, Any]
    unreal_return_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    def expected_sha256(self) -> str:
        return canonical_sha256(self, "manifest_sha256")

    @model_validator(mode="after")
    def validate_hash(self) -> ProvenanceManifest:
        if self.manifest_sha256 != self.expected_sha256():
            raise ValueError("Provenance manifest hash mismatch")
        return self


class VerifiedDeliveryRecord(BaseModel):
    schema_id: Literal["artflow-verified-delivery/1"] = "artflow-verified-delivery/1"
    run_id: str
    return_receipt: UnrealReturnReceipt
    provenance_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    verification_report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    visible_evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["verified_with_declared_c2pa_limitation"]
    delivery_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    def expected_sha256(self) -> str:
        return canonical_sha256(self, "delivery_sha256")

    @model_validator(mode="after")
    def validate_hash(self) -> VerifiedDeliveryRecord:
        if self.delivery_sha256 != self.expected_sha256():
            raise ValueError("Verified delivery hash mismatch")
        return self


def verify_provenance(
    manifest: ProvenanceManifest,
    request: UnrealReturnRequest,
    receipt: UnrealReturnReceipt,
    root: Path,
) -> ProvenanceVerification:
    checks: list[str] = []
    failures: list[str] = []
    bindings = [manifest.output, *manifest.ingredients]
    verified = 0
    for binding in bindings:
        path = (root / binding.path).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            failures.append(f"missing_or_escaped:{binding.role}")
            continue
        if sha256_file(path) != binding.sha256:
            failures.append(f"hash_mismatch:{binding.role}")
            continue
        verified += 1
    checks.append(f"artifact_bindings:{verified}/{len(bindings)}")
    if request.source.sha256 != manifest.output.sha256:
        failures.append("request_output_binding_mismatch")
    if receipt.request_sha256 != request.request_sha256:
        failures.append("receipt_request_binding_mismatch")
    if receipt.source_sha256 != manifest.output.sha256:
        failures.append("receipt_output_binding_mismatch")
    if receipt.receipt_sha256 != manifest.unreal_return_receipt_sha256:
        failures.append("receipt_manifest_binding_mismatch")
    labels = set(manifest.assertions)
    expected_labels = {"c2pa.hash.data", "c2pa.actions.v2", "c2pa.ingredient.v3"}
    if not expected_labels.issubset(labels):
        failures.append("missing_c2pa_assertion_vocabulary")
    checks.extend(
        [
            "request_content_hash_valid",
            "receipt_content_hash_valid",
            "manifest_content_hash_valid",
            "c2pa_2.4_vocabulary_present",
        ]
    )
    return ProvenanceVerification(
        status="failed" if failures else "passed_with_declared_limitations",
        hash_chain_valid=not failures,
        c2pa_signature_status="not_present",
        verified_bindings=verified,
        total_bindings=len(bindings),
        checks=checks,
        failures=failures,
        limitations=[
            "This JSON sidecar uses C2PA 2.4 assertion vocabulary but is not a signed JUMBF manifest store.",
            "No c2patool-compatible certificate or signature is present; cryptographic C2PA conformance is not claimed.",
        ],
    )
