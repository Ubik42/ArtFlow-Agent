from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from artflow_agent.pbr import canonical_sha256
from artflow_agent.pbr_unreal import UnrealPBRReturnReceipt, UnrealPBRReturnRequest


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind UE import facts to the same-camera PBR rerender.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--import-result", type=Path, required=True)
    parser.add_argument("--render", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    request = UnrealPBRReturnRequest.model_validate_json(args.request.read_text(encoding="utf-8"))
    result = json.loads(args.import_result.read_text(encoding="utf-8"))
    if result["request_sha256"] != request.request_sha256:
        raise SystemExit("import result is not bound to request")
    facts = {
        "schema_id": "unreal-pbr-return-receipt/1",
        **{key: value for key, value in result.items() if key != "schema_id"},
        "candidate_render_path": args.render.as_posix(),
        "candidate_render_sha256": sha256(args.render),
    }
    facts["receipt_sha256"] = canonical_sha256(facts)
    receipt = UnrealPBRReturnReceipt.model_validate(facts)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(receipt.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
