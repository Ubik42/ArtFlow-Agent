from pathlib import Path

from artflow_agent.camera_move import compile_camera_move_request, execute_blender_camera_move

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m38-s1-camera-move"
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")

request = compile_camera_move_request(project_root=ROOT)
receipt = execute_blender_camera_move(
    request,
    project_root=ROOT,
    output_dir=OUTPUT,
    blender_executable=BLENDER,
)
print(receipt.model_dump_json(indent=2))
