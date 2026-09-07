from pathlib import Path

from artflow_agent.lookdev_handoff import compile_scene_lookdev_request, execute_blender_lookdev

ROOT = Path(__file__).resolve().parents[1]
CONDITIONING = ROOT / "artifacts/goal/m24-s1-scene-conditioning"
SHOT = ROOT / "artifacts/goal/m23-s5-camera-light"
OUTPUT = ROOT / "artifacts/goal/m24-s2-scene-lookdev"
SOURCE_BLEND = SHOT / "AF_ShrineCourtyard_Shot.blend"
BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")

request = compile_scene_lookdev_request(
    session_id="scene-session-dc31f6ed0f4e",
    session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
    source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
    conditioning_request_path=CONDITIONING / "conditioning-request.json",
    conditioning_receipt_path=CONDITIONING / "conditioning-receipt.json",
    accepted_artifact_path=CONDITIONING / "depth-guided-candidate.png",
    shot_request_path=SHOT / "shot-request.json",
    source_blend_path=SOURCE_BLEND,
)
receipt = execute_blender_lookdev(
    request,
    project_root=ROOT,
    source_blend_path=SOURCE_BLEND,
    output_dir=OUTPUT,
    blender_executable=BLENDER,
)
print(f"{receipt.status}: {receipt.request_id} ({receipt.elapsed_seconds}s)")
