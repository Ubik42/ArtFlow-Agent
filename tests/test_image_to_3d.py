from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.image_to_3d import (
    ImageTo3DGenerationReceipt,
    ImageTo3DGenerationRequest,
    MeshAdmissionPolicy,
    UnrealMeshAdmissionReceipt,
    inspect_glb,
)

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/goal/m10-s2-image-to-3d"


def _generation() -> tuple[ImageTo3DGenerationRequest, ImageTo3DGenerationReceipt]:
    request = ImageTo3DGenerationRequest.model_validate_json(
        (EVIDENCE / "generation-request.json").read_text(encoding="utf-8")
    )
    receipt = ImageTo3DGenerationReceipt.model_validate_json(
        (EVIDENCE / "generation-receipt.json").read_text(encoding="utf-8")
    )
    return request, receipt


def test_real_triposr_glb_passes_bounded_preimport_inspection() -> None:
    request, generation = _generation()
    receipt = inspect_glb(
        EVIDENCE / "altar-triposr.glb",
        request,
        generation,
        MeshAdmissionPolicy(),
        inspected_at=datetime.now(UTC),
    )
    assert receipt.status == "admitted"
    assert receipt.vertex_count == 63_044
    assert receipt.triangle_count == 125_834
    assert receipt.external_uri_count == 0
    assert receipt.material_strategy == "vertex_color_engine_material"
    assert receipt.normals_strategy == "generate_in_unreal"


def test_corrupt_or_over_budget_glb_fails_closed(tmp_path: Path) -> None:
    request, generation = _generation()
    corrupt = tmp_path / "corrupt.glb"
    corrupt.write_bytes(b"not-a-glb")
    invalid = inspect_glb(
        corrupt,
        request,
        generation,
        MeshAdmissionPolicy(),
        inspected_at=datetime.now(UTC),
    )
    assert invalid.status == "rejected"
    assert "glb_too_short" in invalid.rejection_reasons

    budget = inspect_glb(
        EVIDENCE / "altar-triposr.glb",
        request,
        generation,
        MeshAdmissionPolicy(max_triangles=100_000),
        inspected_at=datetime.now(UTC),
    )
    assert budget.status == "rejected"
    assert "triangle_budget_exceeded" in budget.rejection_reasons


def test_contracts_reject_extra_authority_and_validate_real_unreal_receipt() -> None:
    request, _ = _generation()
    with pytest.raises(ValidationError):
        ImageTo3DGenerationRequest.model_validate(
            {**request.model_dump(mode="json"), "shell": "powershell"}
        )
    receipt = UnrealMeshAdmissionReceipt.model_validate_json(
        (EVIDENCE / "unreal-admission-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt.engine_version.startswith("5.8.1")
    assert receipt.material_slot_count == receipt.simple_collision_count == 1
    assert receipt.source_scene_sha256_before == receipt.source_scene_sha256_after
