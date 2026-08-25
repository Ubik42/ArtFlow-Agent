from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from PIL import Image, ImageChops, ImageFilter, ImageStat
from pydantic_ai import Agent, BinaryContent

from .domain import (
    ArtBrief,
    AssetCheck,
    CandidateEvaluation,
    CandidateVisualEvaluation,
    VariantDirection,
    VisualJudgment,
)

VISUAL_EVALUATOR_INSTRUCTIONS = """
You are a critical game-environment art director evaluating a controlled iteration.
Compare the source composition (first image) with the candidate (second image). Score exactly four
criteria from 1 to 5: composition, direction, coherence, and constraint_safety. Treat preserve and
avoid constraints as hard requirements. Be concise, name visible evidence, and provide one concrete
revision instruction. Do not reward polish that violates the brief.
""".strip()


class EvaluationRunner(Protocol):
    def run_sync(self, prompt: Any) -> Any: ...


class PydanticAIVisualEvaluator:
    """Explicitly opt-in multimodal judgment; never called by deterministic evaluation."""

    def __init__(self, model: str | None = None, *, runner: EvaluationRunner | None = None) -> None:
        if runner is None and model is None:
            raise ValueError("A visual-capable PydanticAI model or test runner is required")
        self.runner = runner or Agent(
            model,
            output_type=VisualJudgment,
            instructions=VISUAL_EVALUATOR_INSTRUCTIONS,
            retries=2,
        )

    def evaluate(
        self,
        candidate_id: str,
        brief: ArtBrief,
        direction: VariantDirection,
        source_path: Path,
        candidate_path: Path,
    ) -> CandidateVisualEvaluation:
        prompt = (
            "Evaluate this candidate.\n"
            f"Intent: {brief.intent}\n"
            f"Direction: {direction.visual_goal}; {direction.prompt_delta}\n"
            f"Preserve: {', '.join(brief.preserve)}\n"
            f"Avoid: {', '.join(brief.avoid)}\n"
            "Image 1 is the source. Image 2 is the candidate."
        )
        result = self.runner.run_sync(
            [
                prompt,
                BinaryContent(
                    data=source_path.read_bytes(), media_type=_image_media_type(source_path)
                ),
                BinaryContent(
                    data=candidate_path.read_bytes(), media_type=_image_media_type(candidate_path)
                ),
            ]
        )
        judgment = VisualJudgment.model_validate(result.output)
        scores = {criterion.name: criterion.score for criterion in judgment.criteria}
        required = {"composition", "direction", "coherence", "constraint_safety"}
        if set(scores) != required:
            raise ValueError("Visual evaluator must return each required criterion exactly once")
        overall = sum(scores.values()) / len(scores)
        return CandidateVisualEvaluation(
            candidate_id=candidate_id,
            passed=overall >= 3.5 and min(scores.values()) >= 3,
            overall_score=round(overall, 2),
            judgment=judgment,
        )


def evaluate_candidate(
    candidate_id: str,
    source_path: Path,
    candidate_path: Path,
    *,
    mask_path: Path | None = None,
) -> CandidateEvaluation:
    with Image.open(source_path) as source_file, Image.open(candidate_path) as candidate_file:
        source = source_file.convert("RGB")
        candidate = candidate_file.convert("RGB")
    source_aspect = source.width / source.height
    candidate_aspect = candidate.width / candidate.height
    aspect_delta = abs(source_aspect - candidate_aspect) / source_aspect
    resized_source = source.resize(candidate.size, Image.Resampling.LANCZOS)
    edge_similarity = _edge_similarity(resized_source, candidate)
    luminance_stddev = ImageStat.Stat(candidate.convert("L")).stddev[0]

    checks = [
        AssetCheck(
            name="minimum_resolution",
            passed=min(candidate.size) >= 512,
            value=f"{candidate.width}x{candidate.height}",
            threshold="short edge >= 512",
            detail="Candidate has enough resolution for portfolio review",
        ),
        AssetCheck(
            name="aspect_ratio_preserved",
            passed=aspect_delta <= 0.02,
            value=round(aspect_delta, 4),
            threshold=0.02,
            detail="Candidate aspect ratio remains aligned with the source composition",
        ),
        AssetCheck(
            name="structural_edge_similarity",
            passed=edge_similarity >= 0.35,
            value=round(edge_similarity, 4),
            threshold=0.35,
            detail="Low-resolution edge structure remains correlated with the source",
        ),
        AssetCheck(
            name="luminance_range",
            passed=luminance_stddev >= 12,
            value=round(luminance_stddev, 2),
            threshold=12,
            detail="Candidate is not visually collapsed to a nearly flat image",
        ),
    ]
    if mask_path is not None:
        checks.append(_outside_mask_check(resized_source, candidate, mask_path))
    return CandidateEvaluation(
        candidate_id=candidate_id,
        passed=all(check.passed for check in checks),
        checks=checks,
    )


def _edge_similarity(source: Image.Image, candidate: Image.Image) -> float:
    size = (128, 128)
    source_edges = source.convert("L").filter(ImageFilter.FIND_EDGES).resize(size)
    candidate_edges = candidate.convert("L").filter(ImageFilter.FIND_EDGES).resize(size)
    difference = ImageChops.difference(source_edges, candidate_edges)
    mean_difference = ImageStat.Stat(difference).mean[0]
    return max(0.0, 1.0 - mean_difference / 255.0)


def _outside_mask_check(source: Image.Image, candidate: Image.Image, mask_path: Path) -> AssetCheck:
    with Image.open(mask_path) as mask_file:
        mask = mask_file.convert("L").resize(candidate.size, Image.Resampling.BILINEAR)
    outside = ImageChops.invert(mask)
    difference = ImageChops.difference(source, candidate)
    changed = sum(ImageStat.Stat(difference, mask=outside).mean) / 3
    return AssetCheck(
        name="unmasked_region_stability",
        passed=changed <= 18,
        value=round(changed, 2),
        threshold=18,
        detail="Mean pixel change outside the requested mask stays bounded",
    )


def _image_media_type(path: Path) -> str:
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        path.suffix.lower(), "image/png"
    )
