from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

from artflow_agent.pbr import CompiledPBRWorkflow


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit one compiled, reviewed PBR workflow.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8190")
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=600.0)
    args = parser.parse_args()

    compiled = CompiledPBRWorkflow.model_validate_json(args.compiled.read_text(encoding="utf-8"))
    started = time.monotonic()
    with httpx.Client(base_url=args.endpoint, timeout=30.0) as client:
        response = client.post("/prompt", json={"prompt": compiled.workflow})
        response.raise_for_status()
        prompt_id = response.json()["prompt_id"]
        while time.monotonic() - started < args.timeout:
            history = client.get(f"/history/{prompt_id}")
            history.raise_for_status()
            payload = history.json()
            if prompt_id in payload:
                entry = payload[prompt_id]
                status = entry.get("status", {})
                if status.get("completed"):
                    break
            time.sleep(1.0)
        else:
            raise TimeoutError(f"reviewed PBR workflow timed out: {prompt_id}")

    result = {
        "schema_id": "artflow-reviewed-pbr-provider-receipt/1",
        "prompt_id": prompt_id,
        "request_id": compiled.request_id,
        "workflow_sha256": compiled.workflow_sha256,
        "capability_snapshot_sha256": compiled.capability_snapshot_sha256,
        "execution_seconds": round(time.monotonic() - started, 3),
        "history": entry,
    }
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in result if key != "history"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
