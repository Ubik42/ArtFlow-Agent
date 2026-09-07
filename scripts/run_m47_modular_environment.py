from pathlib import Path

from artflow_agent.modular_environment import (
    compile_modular_environment_request,
    execute_blender_assembly,
    execute_module_zones,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m47-s1-modular-environment"
request = compile_modular_environment_request(root=ROOT, session_id="scene-session-dc31f6ed0f4e")
(OUTPUT / "modular-environment-request.json").parent.mkdir(parents=True, exist_ok=True)
(OUTPUT / "modular-environment-request.json").write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
zones = execute_module_zones(request, output_dir=OUTPUT, comfy_url="http://127.0.0.1:8188")
assembly = execute_blender_assembly(request, root=ROOT, output_dir=OUTPUT,
                                    blender_executable=Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"))
print(zones.receipt_sha256)
print(assembly["receipt_sha256"])
