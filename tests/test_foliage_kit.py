from pathlib import Path

from artflow_agent.foliage_kit import compile_foliage_kit_request

ROOT = Path(__file__).resolve().parents[1]


def test_foliage_request_binds_biome_candidate_and_finite_recipes() -> None:
    request = compile_foliage_kit_request(root=ROOT, session_id="scene-session-dc31f6ed0f4e")
    assert request.instance_budget == 18
    assert {item.species_id for item in request.species} == {"reed", "fern", "broadleaf"}
    assert request.source_candidate_scene_path.endswith("Terrain_B_dfa6418e8729")
    assert request.unreal_capability_id == "unreal.pcg.biome_foliage_wind.v1"
