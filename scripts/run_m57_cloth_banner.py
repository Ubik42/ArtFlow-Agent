from pathlib import Path

from artflow_agent.cloth_banner import (
    compile_cloth_banner_request,
    execute_banner_texture,
    execute_blender_cloth_banner,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m57-s1-cloth-banner"
request = compile_cloth_banner_request(root=ROOT, session_id="scene-session-dc31f6ed0f4e")
OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "cloth-banner-request.json").write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
texture = execute_banner_texture(request, output_dir=OUTPUT, comfy_url="http://127.0.0.1:8188")
blender = execute_blender_cloth_banner(
    request,
    root=ROOT,
    output_dir=OUTPUT,
    blender_executable=Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"),
)
print(texture.receipt_sha256)
print(blender["receipt_sha256"])
