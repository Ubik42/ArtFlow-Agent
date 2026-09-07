from pathlib import Path

from artflow_agent.blender_set_dressing import compile_set_dressing_request, execute_set_dressing

ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "artifacts/goal/m26-s1-surface-bake"
OUTPUT = ROOT / "artifacts/goal/m28-s1-set-dressing"

request = compile_set_dressing_request(
    session_id="scene-session-dc31f6ed0f4e",
    session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
    source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
    surface_request_path=SURFACE / "surface-request.json",
    surface_receipt_path=SURFACE / "surface-receipt.json",
    source_blend_path=SURFACE / "AF_ShrineCourtyard_Baked.blend",
)
receipt = execute_set_dressing(
    request, project_root=ROOT, source_blend_path=SURFACE / "AF_ShrineCourtyard_Baked.blend",
    output_dir=OUTPUT,
    blender_executable=Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"),
)
print(receipt.model_dump_json(indent=2))
