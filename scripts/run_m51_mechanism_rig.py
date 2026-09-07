from pathlib import Path

from artflow_agent.mechanism_rig import (
    compile_mechanism_rig_request,
    execute_blender_mechanism,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m51-s1-mechanism-rig"
request = compile_mechanism_rig_request(root=ROOT, session_id="scene-session-dc31f6ed0f4e")
receipt = execute_blender_mechanism(
    request,
    root=ROOT,
    output_dir=OUTPUT,
    blender_executable=Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"),
)
print(request.request_sha256)
print(receipt["receipt_sha256"])
