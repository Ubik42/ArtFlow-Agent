from __future__ import annotations

import argparse
from pathlib import Path

from artflow_agent.scene_disposition import (
    SceneVariantPublishReceipt,
    SceneVariantPublishRequest,
)
from artflow_agent.scene_variant_review import compile_scene_variant_review_request


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the fixed Unreal variant review handoff.")
    parser.add_argument("--publish-request", type=Path, required=True)
    parser.add_argument("--publish-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    request = SceneVariantPublishRequest.model_validate_json(
        args.publish_request.read_text(encoding="utf-8")
    )
    receipt = SceneVariantPublishReceipt.model_validate_json(
        args.publish_receipt.read_text(encoding="utf-8")
    )
    review = compile_scene_variant_review_request(request, receipt)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(review.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(review.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
