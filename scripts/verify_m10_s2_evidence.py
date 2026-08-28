from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from artflow_agent.contracts import MultiDomainSceneDeltaPlan
from artflow_agent.image_to_3d import (
    GLBInspectionReceipt,
    ImageTo3DGenerationReceipt,
    ImageTo3DGenerationRequest,
    MeshAdmissionPolicy,
    UnrealMeshAdmissionReceipt,
    UnrealMeshAdmissionRequest,
    file_sha256,
    inspect_glb,
)
from artflow_agent.scene_lifecycle import canonical_sha256
from artflow_agent.scene_orchestration import CapabilityAttestation, compile_multi_domain_dry_run

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/goal/m10-s2-image-to-3d"


def main() -> int:
    request = ImageTo3DGenerationRequest.model_validate_json(
        (EVIDENCE / "generation-request.json").read_text(encoding="utf-8")
    )
    generation = ImageTo3DGenerationReceipt.model_validate_json(
        (EVIDENCE / "generation-receipt.json").read_text(encoding="utf-8")
    )
    inspection = GLBInspectionReceipt.model_validate_json(
        (EVIDENCE / "glb-inspection.json").read_text(encoding="utf-8")
    )
    unreal_request = UnrealMeshAdmissionRequest.model_validate_json(
        (EVIDENCE / "unreal-admission-request.json").read_text(encoding="utf-8")
    )
    unreal_receipt = UnrealMeshAdmissionReceipt.model_validate_json(
        (EVIDENCE / "unreal-admission-receipt.json").read_text(encoding="utf-8")
    )
    stage = json.loads((EVIDENCE / "stage-receipt.json").read_text(encoding="utf-8"))
    stage_hash = stage.pop("receipt_sha256")
    assert canonical_sha256(stage) == stage_hash
    stage["receipt_sha256"] = stage_hash

    assert generation.request_sha256 == request.request_sha256
    assert generation.glb_sha256 == inspection.candidate_sha256 == unreal_request.candidate_sha256
    assert inspection.status == "admitted"
    assert inspection.external_uri_count == 0 and not inspection.unsupported_extensions
    assert file_sha256(EVIDENCE / "TRIPOSR-LICENSE.txt") == request.license_sha256
    assert file_sha256(EVIDENCE / "altar-reference.png") == request.source_image_sha256
    assert file_sha256(EVIDENCE / "altar-triposr.glb") == generation.glb_sha256
    assert unreal_receipt.request_sha256 == unreal_request.request_sha256
    assert unreal_receipt.vertex_count == 2_413 and unreal_receipt.triangle_count == 4_817
    assert unreal_receipt.material_slot_count == unreal_receipt.simple_collision_count == 1
    assert unreal_receipt.source_scene_sha256_before == unreal_receipt.source_scene_sha256_after
    assert stage["admission_receipt_sha256"] == unreal_receipt.receipt_sha256
    assert abs(stage["result_longest_extent_cm"] - 180.0) <= 1e-4
    assert file_sha256(EVIDENCE / "unreal-generated-altar-v3.png") == stage["screenshot_sha256"]

    hostile = inspect_glb(
        EVIDENCE / "altar-triposr.glb",
        request,
        generation,
        MeshAdmissionPolicy(max_triangles=100_000),
        inspected_at=datetime.now(UTC),
    )
    assert hostile.status == "rejected"
    assert hostile.rejection_reasons == ["triangle_budget_exceeded"]
    (EVIDENCE / "triangle-budget-rejection.json").write_text(
        hostile.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )

    plan = MultiDomainSceneDeltaPlan.model_validate_json(
        (ROOT / "examples/m9-ruin-altar-scene-delta-plan.json").read_text(encoding="utf-8")
    )
    capabilities = [
        CapabilityAttestation.model_validate(item)
        for item in json.loads(
            (ROOT / "examples/m9-capability-attestations.json").read_text(encoding="utf-8")
        )
    ]
    observed = {
        target_id: fingerprint
        for operation in plan.operations
        for target_id, fingerprint in operation.expected_source_fingerprints.items()
    }
    fallback = compile_multi_domain_dry_run(plan, capabilities, observed)
    asset_route = next(item for item in fallback.routes if item.domain == "asset")
    assert asset_route.tool_name == "asset.catalog.query"
    assert fallback.committed_mutation_count == 0 and fallback.source_scene_unchanged

    result = {
        "schema_id": "m10-s2-independent-verification/1",
        "status": "verified",
        "provider": request.model_id,
        "provider_revision": request.provider_revision,
        "license_spdx": request.license_spdx,
        "external_submission_count": generation.external_submission_count,
        "estimated_cost_usd": generation.estimated_cost_usd,
        "generation_elapsed_seconds": generation.elapsed_seconds,
        "glb_size_bytes": generation.glb_size_bytes,
        "preimport_vertices": inspection.vertex_count,
        "preimport_triangles": inspection.triangle_count,
        "unreal_vertices": unreal_receipt.vertex_count,
        "unreal_triangles": unreal_receipt.triangle_count,
        "unreal_material_slots": unreal_receipt.material_slot_count,
        "unreal_simple_collisions": unreal_receipt.simple_collision_count,
        "staged_extent_cm": stage["result_longest_extent_cm"],
        "hostile_triangle_budget_rejected": True,
        "project_asset_fallback_tool": asset_route.tool_name,
        "source_scene_unchanged": True,
        "duplicate_side_effect_count": 0,
    }
    result["verification_sha256"] = canonical_sha256(result)
    (EVIDENCE / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
