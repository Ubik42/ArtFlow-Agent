from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAVED = (
    ROOT
    / "integrations/unreal/ArtFlowBridgeHost/Saved/ArtFlowSceneBridge/CurrentVariant"
)
OUTPUT = ROOT / "artifacts/goal/m21-s1-current-publish"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=(
            "publish-created",
            "publish-reconciled",
            "review-inspected",
            "review-reconciled",
        ),
    )
    args = parser.parse_args()
    kind = "publish" if args.phase.startswith("publish") else "review"
    expected = {
        "publish-created": "published",
        "publish-reconciled": "reconciled",
        "review-inspected": "inspected",
        "review-reconciled": "reconciled",
    }[args.phase]
    matches = sorted(SAVED.glob(f"scene-{kind}-*/{kind}-receipt.json"))
    if len(matches) != 1:
        raise SystemExit(f"expected one current {kind} receipt, got {matches}")
    source = matches[0]
    text = source.read_text(encoding="utf-8-sig")
    if f'"status": "{expected}"' not in text:
        raise SystemExit(f"current {kind} receipt is not {expected}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, OUTPUT / f"{args.phase}-receipt.json")


if __name__ == "__main__":
    main()
