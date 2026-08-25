from types import SimpleNamespace

from PIL import Image, ImageDraw

from artflow_agent.domain import ArtBrief, VariantDirection, VisualCriterion, VisualJudgment
from artflow_agent.evaluation import PydanticAIVisualEvaluator, evaluate_candidate


def test_candidate_evaluation_catches_flat_or_misaligned_output(tmp_path) -> None:
    source = tmp_path / "source.png"
    good = tmp_path / "good.png"
    flat = tmp_path / "flat.png"
    image = Image.new("RGB", (768, 512), "#596167")
    draw = ImageDraw.Draw(image)
    draw.rectangle((180, 90, 590, 430), fill="#b9b9b2")
    draw.rectangle((310, 190, 460, 430), fill="#30383b")
    for x in range(80, 690, 80):
        for y in range(60, 460):
            image.putpixel((x, y), (190, 190, 185))
    image.save(source)
    image.save(good)
    Image.new("RGB", (512, 768), "#777777").save(flat)

    assert evaluate_candidate("good", source, good).passed is True
    failed = evaluate_candidate("flat", source, flat)
    assert failed.passed is False
    assert {check.name for check in failed.checks if not check.passed} >= {
        "aspect_ratio_preserved",
        "luminance_range",
    }


def test_visual_evaluator_applies_fixed_pass_rule(tmp_path) -> None:
    image = tmp_path / "image.png"
    Image.new("RGB", (32, 32), "#777777").save(image)
    judgment = VisualJudgment(
        criteria=[
            VisualCriterion(name="composition", score=4, rationale="preserved"),
            VisualCriterion(name="direction", score=4, rationale="clear"),
            VisualCriterion(name="coherence", score=4, rationale="coherent"),
            VisualCriterion(name="constraint_safety", score=3, rationale="safe"),
        ],
        revision_instruction="Strengthen the focal lighting.",
    )
    runner = SimpleNamespace(run_sync=lambda _: SimpleNamespace(output=judgment))
    brief = ArtBrief(
        project_name="fixture",
        source_image=str(image),
        intent="Create one controlled environment lighting direction.",
    )
    direction = VariantDirection(
        name="cold-storm",
        visual_goal="Cold light before a storm",
        prompt_delta="cool palette",
        recipe_id="composition-preserving-v1",
    )

    result = PydanticAIVisualEvaluator(runner=runner).evaluate(
        "candidate", brief, direction, image, image
    )
    assert result.passed is True
    assert result.overall_score == 3.75
