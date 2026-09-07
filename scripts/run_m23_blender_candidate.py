from __future__ import annotations

from pathlib import Path

from artflow_agent.blender_modeling import (
    compile_weathered_shrine_request,
    execute_blender_modeling,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m23-s1-blender-modeling"
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")


request = compile_weathered_shrine_request(
    session_id="scene-session-dc31f6ed0f4e",
    session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
    source_scene="/Game/ArtFlowDemo",
    source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
    width_cm=360,
    depth_cm=240,
    height_cm=320,
    tier_count=3,
    pillar_count=4,
    detail_level=3,
    seed=240907,
    palette="basalt_moss",
    output_stem="AF_WeatheredShrine",
)
receipt = execute_blender_modeling(
    request,
    project_root=ROOT,
    output_dir=OUTPUT,
    blender_executable=BLENDER,
)
print(receipt.model_dump_json(indent=2))
