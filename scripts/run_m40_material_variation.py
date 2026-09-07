from pathlib import Path

from artflow_agent.material_variation import (
    compile_material_variation_request,
    execute_material_variation,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m40-s1-material-variation"
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")

request = compile_material_variation_request(
    conditioning_receipt_path=ROOT
    / "artifacts/goal/m24-s1-scene-conditioning/conditioning-receipt.json",
    procedural_kit_receipt_path=ROOT
    / "artifacts/goal/m32-s1-procedural-kit/procedural-kit-receipt.json",
    native_pcg_receipt_path=ROOT
    / "artifacts/goal/m34-s1-pcg-density/unreal-native-pcg-density-receipt.json",
    session_id="scene-session-dc31f6ed0f4e",
    session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
)
receipt = execute_material_variation(
    request,
    project_root=ROOT,
    output_dir=OUTPUT,
    blender_executable=BLENDER,
)
print(receipt.model_dump_json(indent=2))
