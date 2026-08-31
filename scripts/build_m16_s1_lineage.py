from __future__ import annotations

import argparse
from pathlib import Path

from artflow_agent.scene_disposition import (
    SceneVariantPublishReceipt,
    SceneVariantPublishRequest,
)
from artflow_agent.scene_session import SceneCandidateDomainEvaluation
from artflow_agent.scene_variant_review import (
    SceneVariantReviewReceipt,
    SceneVariantReviewRequest,
    compile_scene_variant_lineage,
)


def load(model, path: Path):
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the frozen scene variant lineage.")
    parser.add_argument("--failed-evaluation", type=Path, required=True)
    parser.add_argument("--corrected-evaluation", type=Path, required=True)
    parser.add_argument("--publish-request", type=Path, required=True)
    parser.add_argument("--publish-receipt", type=Path, required=True)
    parser.add_argument("--review-request", type=Path, required=True)
    parser.add_argument("--review-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    lineage = compile_scene_variant_lineage(
        failed=load(SceneCandidateDomainEvaluation, args.failed_evaluation),
        corrected=load(SceneCandidateDomainEvaluation, args.corrected_evaluation),
        publish_request=load(SceneVariantPublishRequest, args.publish_request),
        publish_receipt=load(SceneVariantPublishReceipt, args.publish_receipt),
        review_request=load(SceneVariantReviewRequest, args.review_request),
        review_receipt=load(SceneVariantReviewReceipt, args.review_receipt),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(lineage.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(lineage.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
