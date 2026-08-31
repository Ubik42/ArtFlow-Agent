from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from artflow_agent.pbr import (
    ComfyCapabilitySnapshot,
    PBRCompileRequest,
    PBRWorkflowCompiler,
)

ROOT = Path(__file__).resolve().parents[1]


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile the reviewed ArtFlow PBR fixture.")
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--material-id", default="ruin_altar_basalt")
    parser.add_argument("--source-image", default="ArtFlow/M7/candidate-beauty.png")
    parser.add_argument(
        "--visual-intent",
        default="风化玄武岩祭坛，深灰基色，细微暖色矿物纹理，粗糙且适合废墟场景",
    )
    parser.add_argument("--negative-prompt", default="文字，水印，透视，相机阴影，烘焙光照，高光，接缝")
    parser.add_argument("--seed", type=int, default=240827)
    parser.add_argument("--size", type=int, choices=(512, 768, 1024, 1536, 2048), default=1024)
    parser.add_argument(
        "--template", type=Path, default=ROOT / "recipes/pbr-material-v1.template.json"
    )
    parser.add_argument(
        "--workflow", type=Path, default=ROOT / "recipes/pbr-material-v1.workflow.json"
    )
    args = parser.parse_args()

    snapshot = ComfyCapabilitySnapshot.model_validate_json(
        args.snapshot.read_text(encoding="utf-8")
    )
    compiler = PBRWorkflowCompiler(
        args.template,
        args.workflow,
    )
    request = PBRCompileRequest(
        material_id=args.material_id,
        source_image=args.source_image,
        source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest(),
        visual_intent=args.visual_intent,
        negative_prompt=args.negative_prompt,
        seed=args.seed,
        denoise=1.0 if compiler.template.template_id == "pbr-material-synthesis-v1" else 0.45,
        width=args.size,
        height=args.size,
        tileable=True,
    )
    compiled = compiler.compile(request, snapshot)
    atomic_write(args.output, compiled.model_dump_json(indent=2) + "\n")
    print(compiled.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
