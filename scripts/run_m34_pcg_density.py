from pathlib import Path

from artflow_agent.pcg_density import compile_pcg_density_request, execute_pcg_density

ROOT = Path(__file__).resolve().parents[1]
M24 = ROOT / "artifacts/goal/m24-s1-scene-conditioning"
M32 = ROOT / "artifacts/goal/m32-s1-procedural-kit"
OUTPUT = ROOT / "artifacts/goal/m34-s1-pcg-density"
request = compile_pcg_density_request(
    session_id="scene-session-dc31f6ed0f4e",
    scene_package_sha256="ca79f77b487ea5080876017d513f815c37846eb80edea2b33c4d990b7f07ecf6",
    depth_path=M24 / "depth-normalized.png",
    kit_receipt_path=M32 / "procedural-kit-receipt.json",
    kit_manifest_path=M32 / "AF_Wayfinder_Kit-manifest.json",
)
OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "pcg-density-request.json").write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
receipt = execute_pcg_density(request, output_dir=OUTPUT, comfy_url="http://127.0.0.1:8190")
print(receipt.model_dump_json(indent=2))
