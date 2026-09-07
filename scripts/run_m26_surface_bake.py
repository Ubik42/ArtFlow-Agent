from pathlib import Path

from artflow_agent.blender_surface import compile_surface_request, execute_surface_bake

ROOT = Path(__file__).resolve().parents[1]
LOOKDEV = ROOT / "artifacts/goal/m24-s2-scene-lookdev"
OUTPUT = ROOT / "artifacts/goal/m26-s1-surface-bake"
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")

objects = [
    {"name": "AF_GN_ShrineCourtyard", "source": "geometry_nodes_output"},
    *[
        {"name": name, "source": "registered_mesh"}
        for name in [
            "AF_Base_01", "AF_Base_02", "AF_Base_03",
            "AF_Pillar_-1_0", "AF_Pillar_-1_1", "AF_Pillar_1_0", "AF_Pillar_1_1",
            "AF_Lintel", "AF_Crown", "AF_Altar", "AF_Inlay",
            *[f"AF_Rubble_{index:02d}" for index in range(1, 16)],
        ]
    ],
]
request = compile_surface_request(
    session_id="scene-session-dc31f6ed0f4e",
    session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
    source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
    lookdev_request_path=LOOKDEV / "lookdev-request.json",
    lookdev_receipt_path=LOOKDEV / "lookdev-receipt.json",
    source_blend_path=LOOKDEV / "AF_ShrineCourtyard_Lookdev.blend",
    objects=objects,
)
receipt = execute_surface_bake(
    request,
    project_root=ROOT,
    source_blend_path=LOOKDEV / "AF_ShrineCourtyard_Lookdev.blend",
    output_dir=OUTPUT,
    blender_executable=BLENDER,
)
print(receipt.model_dump_json(indent=2))
