from pathlib import Path

from artflow_agent.mechanism_shot import compile_mechanism_shot_request

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m53-s1-mechanism-shot"
OUTPUT.mkdir(parents=True, exist_ok=True)
request = compile_mechanism_shot_request(root=ROOT)
(OUTPUT / "mechanism-shot-request.json").write_text(
    request.model_dump_json(indent=2) + "\n", encoding="utf-8"
)
print(request.model_dump_json())
