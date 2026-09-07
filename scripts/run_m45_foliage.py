from pathlib import Path

from artflow_agent.foliage_kit import compile_foliage_kit_request, execute_blender_foliage

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m45-s1-foliage-kit"
request = compile_foliage_kit_request(root=ROOT, session_id="scene-session-dc31f6ed0f4e")
receipt = execute_blender_foliage(
    request, root=ROOT, output_dir=OUTPUT,
    blender_executable=Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"),
)
print(request.request_sha256)
print(receipt["receipt_sha256"])
