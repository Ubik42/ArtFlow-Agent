from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Independent same-camera M13 visual evaluation.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    with Image.open(args.source) as source_image, Image.open(args.candidate) as candidate_image:
        source = source_image.convert("RGB")
        candidate = candidate_image.convert("RGB")
        if source.size != candidate.size:
            raise SystemExit("same-camera evaluation requires equal render dimensions")
        difference = ImageChops.difference(source, candidate)
        changed = ImageStat.Stat(difference)
        mean_abs_change = sum(changed.mean) / 3.0
        source_luma = ImageStat.Stat(source.convert("L")).mean[0]
        candidate_luma = ImageStat.Stat(candidate.convert("L")).mean[0]
        width, height = source.size
        protected_box = (int(width * 0.27), int(height * 0.42), int(width * 0.47), int(height * 0.77))
        protected_change = sum(
            ImageStat.Stat(difference.crop(protected_box)).mean
        ) / 3.0
    result = {
        "schema_id": "artflow-m13-independent-visual-evaluation/1",
        "evaluator": "same-camera-pixel-critic/1",
        "generator_independent": True,
        "plan_id": plan["plan_id"],
        "plan_sha256": plan["plan_sha256"],
        "source_render_sha256": sha256(args.source),
        "candidate_render_sha256": sha256(args.candidate),
        "same_dimensions": True,
        "mean_absolute_change": round(mean_abs_change, 6),
        "protected_proxy_change": round(protected_change, 6),
        "source_mean_luma": round(source_luma, 6),
        "candidate_mean_luma": round(candidate_luma, 6),
        "verdict": "pass" if mean_abs_change >= 2.0 and protected_change < 12.0 else "reject",
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["verdict"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
