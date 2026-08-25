from artflow_agent.domain import ArtBrief
from artflow_agent.planning import DeterministicPlanner


def test_plan_preserves_user_constraints() -> None:
    brief = ArtBrief(
        project_name="fixture",
        source_image="fixture.png",
        intent="Create three art-directed environment variants.",
        preserve=["composition"],
        avoid=["characters"],
    )

    plan = DeterministicPlanner().create_plan(brief)

    assert len(plan.directions) == 3
    assert plan.approval_required is True
    assert plan.preserved_constraints == ["composition"]
    assert plan.prohibited_changes == ["characters"]


def test_plan_supports_all_allowed_variant_counts() -> None:
    brief = ArtBrief(
        project_name="fixture",
        source_image="fixture.png",
        intent="Create six distinct environment art directions.",
        variant_count=6,
    )
    assert len(DeterministicPlanner().create_plan(brief).directions) == 6


def test_masked_task_uses_local_refinement_directions() -> None:
    brief = ArtBrief(
        project_name="fixture",
        task_type="masked_refinement",
        source_image="fixture.png",
        intent="Repair only the masked stone edge in the source image.",
        variant_count=1,
    )
    direction = DeterministicPlanner().create_plan(brief).directions[0]
    assert direction.name == "edge-cleanup"
    assert direction.recipe_id == "masked-refinement-v1"
