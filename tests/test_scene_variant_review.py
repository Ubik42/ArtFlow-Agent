from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.scene_disposition import (
    SceneVariantPublishReceipt,
    SceneVariantPublishRequest,
    canonical_sha256,
)
from artflow_agent.scene_session import SceneCandidateDomainEvaluation
from artflow_agent.scene_variant_review import (
    SceneVariantReviewReceipt,
    SceneVariantReviewRequest,
    compile_scene_variant_lineage,
    compile_scene_variant_review_request,
)

ROOT = Path(__file__).resolve().parents[1]
M13 = ROOT / "artifacts/goal/m13-s2-sunlit-overgrown"
M15 = ROOT / "artifacts/goal/m15-s1-session-publish"


def inputs() -> tuple[
    SceneCandidateDomainEvaluation,
    SceneCandidateDomainEvaluation,
    SceneVariantPublishRequest,
    SceneVariantPublishReceipt,
]:
    return (
        SceneCandidateDomainEvaluation.model_validate_json(
            (M13 / "failure-domain-evaluation.json").read_text(encoding="utf-8")
        ),
        SceneCandidateDomainEvaluation.model_validate_json(
            (M13 / "corrected-domain-evaluation.json").read_text(encoding="utf-8")
        ),
        SceneVariantPublishRequest.model_validate_json(
            (M15 / "publish-request.json").read_text(encoding="utf-8")
        ),
        SceneVariantPublishReceipt.model_validate_json(
            (M15 / "publish-reconcile-receipt.json").read_text(encoding="utf-8")
        ),
    )


def review_receipt(request: SceneVariantReviewRequest) -> SceneVariantReviewReceipt:
    _, _, _, publish_receipt = inputs()
    payload = {
        "schema_id": "artflow-scene-variant-review-receipt/1",
        "review_id": request.review_id,
        "review_sha256": request.review_sha256,
        "status": "inspected",
        "engine_version": "5.8.1-test",
        "published_scene": request.published_scene,
        "published_level_sha256": publish_receipt.published_level_sha256,
        "source_level_sha256_before": request.source_level_sha256,
        "source_level_sha256_after": request.source_level_sha256,
        "protected_state_sha256": request.expected_protected_state_sha256,
        "material_path": request.expected_material_path,
        "generated_instance_count": request.expected_instance_count,
        "source_save_count": 0,
        "completed_at": "2026-08-30T00:00:00Z",
    }
    payload["receipt_sha256"] = canonical_sha256(payload)
    return SceneVariantReviewReceipt.model_validate(payload)


def test_review_request_is_bound_to_the_reconciled_published_variant() -> None:
    _, _, request, receipt = inputs()
    review = compile_scene_variant_review_request(request, receipt)

    assert review.published_scene == request.decision.published_scene
    assert review.published_level_sha256 == receipt.published_level_sha256
    assert review.idempotency_key == f"scene-review:{review.review_sha256}"


def test_review_request_cannot_be_resealed_for_an_arbitrary_map() -> None:
    _, _, request, receipt = inputs()
    payload = json.loads(compile_scene_variant_review_request(request, receipt).model_dump_json())
    payload["published_scene"] = "/Game/ArtFlow/Published/Other"
    unsigned = {
        key: value
        for key, value in payload.items()
        if key not in {"schema_id", "review_id", "review_sha256", "idempotency_key"}
    }
    digest = canonical_sha256(unsigned)
    payload["review_id"] = f"scene-review-{digest[:16]}"
    payload["review_sha256"] = digest
    payload["idempotency_key"] = f"scene-review:{digest}"

    with pytest.raises(ValidationError, match="registered Published variant"):
        SceneVariantReviewRequest.model_validate(payload)


def test_lineage_retains_four_domains_and_ends_in_real_unreal_review() -> None:
    failed, corrected, request, receipt = inputs()
    review = compile_scene_variant_review_request(request, receipt)
    lineage = compile_scene_variant_lineage(
        failed=failed,
        corrected=corrected,
        publish_request=request,
        publish_receipt=receipt,
        review_request=review,
        review_receipt=review_receipt(review),
    )

    assert lineage.retained_domains == ["image", "material", "asset", "pcg"]
    assert lineage.correction_domain == "lighting"
    assert [step.state for step in lineage.steps] == [
        "retained",
        "failed",
        "corrected",
        "adopted",
        "published",
        "inspected",
    ]
    assert lineage.source_level_unchanged is True
