import json
from pathlib import Path

from artflow_agent.procedural_kit import compile_procedural_kit_request, execute_procedural_kit

ROOT = Path(__file__).resolve().parents[1]
M28 = ROOT / "artifacts/goal/m28-s1-set-dressing"
M30 = ROOT / "artifacts/goal/m30-s1-surface-detail"
OUTPUT = ROOT / "artifacts/goal/m32-s1-procedural-kit"

surface_return = json.loads((M30 / "unreal-surface-detail-return-receipt.json").read_text(encoding="utf-8"))
request = compile_procedural_kit_request(
    session_id="scene-session-dc31f6ed0f4e",
    session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
    source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
    source_candidate_scene_path=surface_return["candidate_scene_path"],
    visual_target_path=M30 / "AF_Inlay_ProjectionTexture.png",
    bounds_path=M28 / "set-dressing-request.json",
)
receipt = execute_procedural_kit(
    request, project_root=ROOT, output_dir=OUTPUT,
    blender_executable=Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"),
)
print(receipt.model_dump_json(indent=2))
