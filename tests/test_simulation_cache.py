from pathlib import Path

from artflow_agent.simulation_cache import compile_simulation_cache_request

ROOT = Path(__file__).resolve().parents[1]


def test_simulation_cache_request_is_bounded_and_source_bound() -> None:
    request = compile_simulation_cache_request(project_root=ROOT)
    assert request.frame_end - request.frame_start + 1 == 72
    assert request.max_cache_bytes == 32 * 1024 * 1024
    assert request.source_candidate_scene_path.endswith("Terrain_B_dfa6418e8729")
    assert request.sequence_asset_path.startswith("/Game/ArtFlow/Sequences/Generated/")
