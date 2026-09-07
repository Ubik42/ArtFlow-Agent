from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.recipes import RecipeCatalog
from artflow_agent.surface_detail import (
    SurfaceDetailRequest,
    compile_surface_detail_request,
)

ROOT = Path(__file__).resolve().parents[1]


def current_request() -> SurfaceDetailRequest:
    surface = ROOT / "artifacts/goal/m26-s1-surface-bake"
    dressing = ROOT / "artifacts/goal/m28-s1-set-dressing"
    return compile_surface_detail_request(
        session_id="scene-session-dc31f6ed0f4e",
        session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
        source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
        surface_request_path=surface / "surface-request.json",
        surface_receipt_path=surface / "surface-receipt.json",
        source_blend_path=surface / "AF_ShrineCourtyard_Baked.blend",
        dressing_return_path=dressing / "unreal-set-dressing-return-receipt.json",
        source_render_path=dressing / "unreal-set-dressing-candidate.png",
    )


def test_surface_detail_binds_current_scene_object_and_fixed_recipe() -> None:
    request = current_request()
    recipe = RecipeCatalog.bundled().get(request.comfy_recipe_id)

    assert request.target_object == "AF_Inlay"
    assert request.source_candidate_scene_path.endswith("Dressing_B_c496854357de")
    assert request.blender_capability_id == "blender.surface.inlay_projection_bake.v1"
    assert recipe.definition.execution_ready is True
    assert {
        "ProductionConstraintCheck",
        "WorkflowContractCheck",
        "GenerationReceipt",
    } <= set(recipe.definition.required_nodes)


def test_surface_detail_rejects_identity_drift() -> None:
    payload = current_request().model_dump(mode="json")
    payload["projection_scale"] = 0.7
    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        SurfaceDetailRequest.model_validate(payload)
