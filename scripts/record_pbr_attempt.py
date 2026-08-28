from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from artflow_agent.pbr import CompiledPBRWorkflow
from artflow_agent.pbr_validation import validate_generation


def main() -> int:
    parser = argparse.ArgumentParser(description="Record and validate one real ComfyUI PBR attempt.")
    parser.add_argument("--compiled", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--execution-seconds", type=float, required=True)
    parser.add_argument("--history", type=Path)
    args = parser.parse_args()
    compiled = CompiledPBRWorkflow.model_validate_json(args.compiled.read_text(encoding="utf-8"))
    channels = ("base_color", "normal", "roughness", "metallic", "ambient_occlusion")
    if args.history is None:
        source_paths = {
            channel: next(args.output_root.glob(f"*_{channel}_*.png")) for channel in channels
        }
    else:
        history = json.loads(args.history.read_text(encoding="utf-8"))[args.prompt_id]
        node_channels = {"26": "base_color", "36": "normal", "46": "roughness", "56": "metallic", "66": "ambient_occlusion"}
        source_paths = {
            channel: args.output_root / history["outputs"][node]["images"][0]["filename"]
            for node, channel in node_channels.items()
        }
    raw_root = args.evidence_dir / "raw"
    raw_root.mkdir(parents=True, exist_ok=True)
    copied: dict[str, Path] = {}
    for channel, source in source_paths.items():
        destination = raw_root / f"ruin_altar_basalt_{channel}.png"
        shutil.copy2(source, destination)
        copied[channel] = destination
    receipt = validate_generation(
        prompt_id=args.prompt_id,
        request_id=compiled.request_id,
        workflow_sha256=compiled.workflow_sha256,
        capability_snapshot_sha256=compiled.capability_snapshot_sha256,
        execution_seconds=args.execution_seconds,
        paths=copied,
        expected_size=(compiled.texture_set.width, compiled.texture_set.height),
    )
    destination = args.evidence_dir / "generation-validation-receipt.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(receipt.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    print(json.dumps(receipt.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0 if receipt.status == "validated" else 2


if __name__ == "__main__":
    raise SystemExit(main())
