from pathlib import Path

from artflow_agent.surface_detail import (
    compile_surface_detail_request,
    execute_blender_surface_detail,
    execute_comfy_surface_detail,
    reconcile_existing_comfy_surface_detail,
)

ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "artifacts/goal/m26-s1-surface-bake"
DRESSING = ROOT / "artifacts/goal/m28-s1-set-dressing"
OUTPUT = ROOT / "artifacts/goal/m30-s1-surface-detail"


def main() -> int:
    request = compile_surface_detail_request(
        session_id="scene-session-dc31f6ed0f4e",
        session_sha256="dc31f6ed0f4e38a179db7854f36aac7ee060bdcbf7218cd0784cb8ea372d192b",
        source_level_sha256="620e481466b40de6dab569737ba782246f85b62a6123ea7e702102ed5d24974a",
        surface_request_path=SURFACE / "surface-request.json",
        surface_receipt_path=SURFACE / "surface-receipt.json",
        source_blend_path=SURFACE / "AF_ShrineCourtyard_Baked.blend",
        dressing_return_path=DRESSING / "unreal-set-dressing-return-receipt.json",
        source_render_path=DRESSING / "unreal-set-dressing-candidate.png",
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "surface-detail-request.json").write_text(
        request.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    comfy_receipt_path = OUTPUT / "comfy-surface-detail-receipt.json"
    if comfy_receipt_path.is_file():
        comfy_receipt = reconcile_existing_comfy_surface_detail(request, OUTPUT)
    else:
        comfy_receipt = execute_comfy_surface_detail(
            request,
            source_render_path=DRESSING / "unreal-set-dressing-candidate.png",
            output_dir=OUTPUT,
        )
    blender_receipt = execute_blender_surface_detail(
        request,
        comfy_receipt,
        project_root=ROOT,
        source_blend_path=SURFACE / "AF_ShrineCourtyard_Baked.blend",
        output_dir=OUTPUT,
        blender_executable=Path(
            "C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"
        ),
    )
    print(comfy_receipt.model_dump_json(indent=2))
    print(blender_receipt.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
