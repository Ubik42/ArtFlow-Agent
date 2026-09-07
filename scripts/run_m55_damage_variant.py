from pathlib import Path

from artflow_agent.damage_variant import (
    compile_damage_variant_request,
    execute_blender_damage,
    execute_damage_field,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m55-s1-damage-variant"
request = compile_damage_variant_request(
    root=ROOT, session_id="scene-session-dc31f6ed0f4e"
)
OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "damage-variant-request.json").write_text(
    request.model_dump_json(indent=2) + "\n", encoding="utf-8"
)
field = execute_damage_field(
    request, output_dir=OUTPUT, comfy_url="http://127.0.0.1:8188"
)
blender = execute_blender_damage(
    request,
    root=ROOT,
    output_dir=OUTPUT,
    blender_executable=Path(
        "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
    ),
)
print(field.receipt_sha256)
print(blender["receipt_sha256"])
