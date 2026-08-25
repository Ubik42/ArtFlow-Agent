from types import SimpleNamespace

from artflow_agent.domain import ArtBrief, RunPlan, VariantDirection
from artflow_agent.planning import PydanticAIPlanner


class FakeRunner:
    def run_sync(self, prompt: str) -> SimpleNamespace:
        assert "fixture" in prompt
        return SimpleNamespace(
            output=RunPlan(
                project_name="wrong",
                approval_required=False,
                directions=[
                    VariantDirection(
                        name="local-fix",
                        visual_goal="Repair the masked stone edge",
                        prompt_delta="clean chipped stone edge",
                        recipe_id="invented-recipe",
                    )
                ],
                preserved_constraints=[],
                prohibited_changes=[],
            )
        )


def test_model_planner_reasserts_user_owned_invariants() -> None:
    brief = ArtBrief(
        project_name="fixture",
        task_type="masked_refinement",
        source_image="source.png",
        intent="Repair only the masked architectural edge.",
        preserve=["camera"],
        avoid=["characters"],
        variant_count=1,
    )
    plan = PydanticAIPlanner(runner=FakeRunner()).create_plan(brief)
    assert plan.project_name == "fixture"
    assert plan.approval_required is True
    assert plan.directions[0].recipe_id == "masked-refinement-v1"
    assert plan.preserved_constraints == ["camera"]
    assert plan.prohibited_changes == ["characters"]
