from __future__ import annotations

import json
from pathlib import Path

from artflow_agent.provenance import (
    EvidenceBinding,
    ProvenanceManifest,
    UnrealReturnReceipt,
    UnrealReturnRequest,
    canonical_sha256,
    sha256_file,
    verify_provenance,
)


def _with_hash(model_type, payload: dict, field: str):
    payload[field] = "0" * 64
    payload[field] = canonical_sha256(payload, field)
    return model_type.model_validate(payload)


def test_unsigned_c2pa_compatible_chain_is_honest_and_tamper_evident(
    tmp_path: Path,
) -> None:
    output = tmp_path / "output.png"
    ingredient = tmp_path / "tribunal.json"
    output.write_bytes(b"png")
    ingredient.write_text(json.dumps({"passed": True}), encoding="utf-8")
    output_binding = EvidenceBinding(
        role="verified_revision",
        path="output.png",
        sha256=sha256_file(output),
        media_type="image/png",
    )
    request = _with_hash(
        UnrealReturnRequest,
        {
            "schema_id": "artflow-unreal-return-request/1",
            "import_id": "return-" + "a" * 20,
            "run_id": "run-test",
            "source": output_binding.model_dump(mode="json"),
            "destination_asset_path": "/Game/ArtFlow/Returns/T_Test",
            "destination_scene_path": "/Game/ArtFlowDemo",
            "source_scene_package_sha256": "1" * 64,
            "adoption_decision_sha256": "2" * 64,
            "tribunal_sha256": "3" * 64,
            "multimodal_tribunal_sha256": "4" * 64,
            "bounded_revision_request_sha256": "5" * 64,
            "bounded_revision_result_sha256": "6" * 64,
            "operation": "import_art_direction_texture_and_bind_scene",
            "authority_scope": "project_local_unreal_fixture",
        },
        "request_sha256",
    )
    receipt = _with_hash(
        UnrealReturnReceipt,
        {
            "schema_id": "artflow-unreal-return-receipt/1",
            "import_id": request.import_id,
            "request_sha256": request.request_sha256,
            "status": "imported",
            "source_sha256": output_binding.sha256,
            "imported_asset_path": "/Game/ArtFlow/Returns/T_Test.T_Test",
            "bound_scene_path": "/Game/ArtFlowDemo",
            "binding_actor_label": "ArtFlow_ReturnPreview",
            "engine_version": "5.8.1",
            "metadata": {"ArtFlow.RunId": "run-test"},
            "completed_at": "2026-08-25T00:00:00Z",
        },
        "receipt_sha256",
    )
    manifest = _with_hash(
        ProvenanceManifest,
        {
            "schema_id": "artflow-c2pa-compatible-provenance/1",
            "c2pa_reference_version": "2.4.0",
            "conformance": "compatible_unsigned_sidecar",
            "claim_generator_info": {
                "name": "ArtFlow Agent",
                "version": "0.1.0",
                "specVersion": "2.4.0",
            },
            "instance_id": "urn:artflow:return:test",
            "title": "Verified revision",
            "output": output_binding.model_dump(mode="json"),
            "ingredients": [
                EvidenceBinding(
                    role="tribunal_report",
                    path="tribunal.json",
                    sha256=sha256_file(ingredient),
                    media_type="application/json",
                ).model_dump(mode="json")
            ],
            "assertions": {
                "c2pa.hash.data": {"alg": "sha256", "hash": output_binding.sha256},
                "c2pa.actions.v2": {"actions": [{"action": "c2pa.opened"}]},
                "c2pa.ingredient.v3": [{"relationship": "inputTo"}],
            },
            "unreal_return_receipt_sha256": receipt.receipt_sha256,
        },
        "manifest_sha256",
    )
    result = verify_provenance(manifest, request, receipt, tmp_path)
    assert result.status == "passed_with_declared_limitations"
    assert result.hash_chain_valid is True
    assert result.c2pa_signature_status == "not_present"
    assert result.verified_bindings == result.total_bindings == 2

    ingredient.write_text("tampered", encoding="utf-8")
    tampered = verify_provenance(manifest, request, receipt, tmp_path)
    assert tampered.status == "failed"
    assert tampered.failures == ["hash_mismatch:tribunal_report"]
