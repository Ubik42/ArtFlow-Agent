from pathlib import Path

from artflow_agent.terrain_biome import (
    compile_terrain_biome_request,
    execute_blender_terrain,
    execute_terrain_fields,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m42-s1-terrain-biome"
OUTPUT.mkdir(parents=True, exist_ok=True)
request = compile_terrain_biome_request(
    depth_path=ROOT / "artifacts/goal/m24-s1-scene-conditioning/depth-normalized.png",
    protected_mask_path=ROOT / "artifacts/goal/m34-s1-pcg-density/protected-exclusion-mask.png",
    material_receipt_path=ROOT / "artifacts/goal/m40-s1-material-variation/unreal-material-variation-receipt.json",
    session_id="scene-session-dc31f6ed0f4e",
)
(OUTPUT / "terrain-biome-request.json").write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
fields = execute_terrain_fields(request, output_dir=OUTPUT, comfy_url="http://127.0.0.1:8188")
terrain = execute_blender_terrain(request, project_root=ROOT, output_dir=OUTPUT,
                                  blender_executable=Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"))
print(fields.model_dump_json(indent=2))
print(terrain["receipt_sha256"])
