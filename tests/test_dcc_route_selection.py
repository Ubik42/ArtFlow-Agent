from pathlib import Path

from artflow_agent.dcc_route_selection import select_dcc_route


def select(intent: str):
    return select_dcc_route(
        project_root=Path(__file__).resolve().parents[1],
        run_id="run-route-test",
        session_id="scene-session-dc31f6ed0f4e",
        session_sha256="a" * 64,
        scene_package_sha256="b" * 64,
        intent=intent,
    )


def test_route_catalog_selects_distinct_shortest_chains() -> None:
    cloth = select("保持构图，探索雨后材质与风中的织物层次")
    damage = select("为门架增加受控破损、旧化和缺口")
    mechanism = select("制作机关开合动画并形成镜头")

    assert cloth.selected_route_id == "cloth_banner"
    assert cloth.selected_stage_capability_ids == [
        "comfy.material.banner_pattern.v1",
        "blender.cloth.banner_authoring.v1",
        "unreal.asset.static_cloth_banner.v1",
    ]
    assert damage.selected_route_id == "damage_variant"
    assert mechanism.selected_route_id == "mechanism_shot"
    assert len({item.decision_sha256 for item in (cloth, damage, mechanism)}) == 3
