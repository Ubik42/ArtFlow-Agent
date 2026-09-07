from pathlib import Path

from artflow_agent.simulation_cache import (
                                           compile_simulation_cache_request,
                                           execute_blender_simulation_cache,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m43-s1-simulation-cache"
request = compile_simulation_cache_request(project_root=ROOT)
receipt = execute_blender_simulation_cache(request, project_root=ROOT, output_dir=OUTPUT,
                                           blender_executable=Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"))
print(receipt.model_dump_json(indent=2))
