from pathlib import Path

from artflow_agent.modular_environment import compile_modular_environment_request

ROOT = Path(__file__).resolve().parents[1]


def test_modular_environment_request_binds_current_scene_and_finite_catalog() -> None:
    request = compile_modular_environment_request(root=ROOT, session_id="scene-session-dc31f6ed0f4e")
    assert request.placement_budget == 12
    assert {item.module_id for item in request.modules} == {"wall", "pillar", "gateway"}
    assert request.source_candidate_scene_path.endswith("Foliage_B_33eb6be804c2")
