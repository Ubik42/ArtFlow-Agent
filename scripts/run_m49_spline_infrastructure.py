from pathlib import Path

from artflow_agent.spline_infrastructure import (
    compile_spline_infrastructure_request,
    execute_blender_spline,
    execute_route_corridor,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m49-s1-spline-infrastructure"
request = compile_spline_infrastructure_request(root=ROOT, session_id="scene-session-dc31f6ed0f4e")
OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "spline-infrastructure-request.json").write_text(
    request.model_dump_json(indent=2) + "\n", encoding="utf-8"
)
corridor = execute_route_corridor(request, output_dir=OUTPUT, comfy_url="http://127.0.0.1:8188")
blender = execute_blender_spline(
    request,
    root=ROOT,
    output_dir=OUTPUT,
    blender_executable=Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"),
)
print(corridor.receipt_sha256)
print(blender["receipt_sha256"])
