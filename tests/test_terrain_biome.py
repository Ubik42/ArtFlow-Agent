from pathlib import Path

from artflow_agent.terrain_biome import compile_terrain_biome_request

ROOT = Path(__file__).resolve().parents[1]


def test_terrain_request_binds_spatial_inputs_and_material_candidate() -> None:
    request = compile_terrain_biome_request(
        depth_path=ROOT / "artifacts/goal/m24-s1-scene-conditioning/depth-normalized.png",
        protected_mask_path=ROOT / "artifacts/goal/m34-s1-pcg-density/protected-exclusion-mask.png",
        material_receipt_path=ROOT / "artifacts/goal/m40-s1-material-variation/unreal-material-variation-receipt.json",
        session_id="scene-session-dc31f6ed0f4e",
    )
    assert request.bounds.width_cm == 1600
    assert request.source_candidate_scene_path.endswith("Material_B_1a77d442c379")
    assert request.comfy_capability_id == "comfy.terrain.height_biome_fields.v1"
