from pathlib import Path

from artflow_agent.shot_package import compile_shot_package_request

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m36-s1-shot-package"
OUTPUT.mkdir(parents=True, exist_ok=True)

request = compile_shot_package_request(
    project_root=ROOT,
    shot_request_path=ROOT / "artifacts/goal/m23-s5-camera-light/shot-request.json",
    shot_receipt_path=ROOT / "artifacts/goal/m23-s5-camera-light/shot-receipt.json",
    native_pcg_receipt_path=(
        ROOT / "artifacts/goal/m34-s1-pcg-density/unreal-native-pcg-density-receipt.json"
    ),
)
(OUTPUT / "shot-package-request.json").write_text(
    request.model_dump_json(indent=2) + "\n", encoding="utf-8"
)
print(request.model_dump_json())
