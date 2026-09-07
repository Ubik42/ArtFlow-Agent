from pathlib import Path

from artflow_agent.procedural_kit import compile_procedural_kit_request


def test_request_binds_visual_target_and_pcg_consumer(tmp_path: Path) -> None:
    visual = tmp_path / "target.png"
    visual.write_bytes(b"registered visual target")
    bounds = tmp_path / "bounds.json"
    bounds.write_text('{"bounds":{"min_m":[-4.8,-4.8,0],"max_m":[4.8,4.8,4]}}')
    request = compile_procedural_kit_request(
        session_id="scene-session-dc31f6ed0f4e",
        session_sha256="a" * 64,
        source_level_sha256="b" * 64,
        source_candidate_scene_path="/Game/ArtFlow/Candidate",
        visual_target_path=visual,
        bounds_path=bounds,
    )
    assert request.variant_count == 3
    assert request.consumer_capability_id == "unreal.pcg.modular_kit_scatter.v1"
    assert request.visual_target_sha256
