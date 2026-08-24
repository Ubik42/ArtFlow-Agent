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

