from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.pbr import CompiledPBRWorkflow
from artflow_agent.pbr_validation import synthesize_dielectric_texture_set, validate_generation


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Correct failed PBR channels from one accepted dielectric albedo."
    )
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--base-color", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--execution-seconds", type=float, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--material-id", default="ruin_altar_basalt")
    args = parser.parse_args()
    compiled = CompiledPBRWorkflow.model_validate_json(args.compiled.read_text(encoding="utf-8"))
    paths = synthesize_dielectric_texture_set(
        args.base_color,
        args.output_dir,
        material_id=args.material_id,
    )
    receipt = validate_generation(
        prompt_id=args.prompt_id,
        request_id=compiled.request_id,
        workflow_sha256=compiled.workflow_sha256,
        capability_snapshot_sha256=compiled.capability_snapshot_sha256,
        execution_seconds=args.execution_seconds,
        paths=paths,
        expected_size=(compiled.texture_set.width, compiled.texture_set.height),
    )
    if receipt.status != "validated":
        raise SystemExit("corrected technical texture set still failed validation")
    temporary = args.receipt.with_suffix(args.receipt.suffix + ".tmp")
    temporary.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.receipt)
    print(json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
