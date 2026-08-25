from __future__ import annotations

from typing import Any, Protocol

from pydantic_ai import Agent

from .domain import ArtBrief, RunPlan, VariantDirection


class Planner(Protocol):
    def create_plan(self, brief: ArtBrief) -> RunPlan: ...


DEFAULT_DIRECTIONS = (
    ("cold-storm", "Cold light before a storm", "cool palette, heavy clouds, crisp silhouette"),
    ("warm-ruins", "Warm sunset over ancient ruins", "warm key light, long shadows, dusty air"),
    (
        "ritual-contrast",
        "High-contrast mysterious ritual",
        "dark ambient light, focused emissive accents",
    ),
    ("fog-depth", "Layered dawn fog", "soft dawn light, aerial perspective, restrained saturation"),
    (
        "moon-silhouette",
        "Moonlit silhouette study",
        "cool moon key, deep values, readable edge light",
    ),
    (
        "weather-break",
        "Light breaking through weather",
        "volumetric light break, wet surfaces, clearing sky",
    ),
)

MASKED_DIRECTIONS = (
    (
        "edge-cleanup",
        "Resolve the masked silhouette",
        "clean edge hierarchy, preserve adjacent forms",
    ),
    (
        "material-match",
        "Match the surrounding material",
        "local material continuity, matching roughness",
    ),
    (
        "light-integration",
        "Integrate the patch into the lighting",
        "matched light direction and contact shadow",
    ),
    (
        "detail-balance",
        "Balance local surface detail",
        "controlled detail frequency, no new focal point",
    ),
    (
        "wear-pass",
        "Add restrained environmental wear",
        "subtle wear consistent with nearby surfaces",
    ),
    (
        "artifact-removal",
        "Remove generation artifacts",
        "coherent edges, clean texture transitions",
    ),
)


class DeterministicPlanner:
    """Safe placeholder that keeps the application runnable before LLM integration."""

    def create_plan(self, brief: ArtBrief) -> RunPlan:
        recipe_id = (
            "masked-refinement-v1"
            if brief.task_type == "masked_refinement"
            else "composition-preserving-v1"
        )
        source_directions = (
            MASKED_DIRECTIONS if brief.task_type == "masked_refinement" else DEFAULT_DIRECTIONS
        )
        directions = [
            VariantDirection(
                name=name,
                visual_goal=goal,
                prompt_delta=delta,
                recipe_id=recipe_id,
            )
            for name, goal, delta in source_directions[: brief.variant_count]
        ]
        return RunPlan(
            project_name=brief.project_name,
            directions=directions,
            preserved_constraints=brief.preserve,
            prohibited_changes=brief.avoid,
        )


PLANNER_INSTRUCTIONS = """
You are the planning layer for a narrow game-art iteration pipeline.
Return concrete, visually distinct directions without inventing new user constraints.
Use composition-preserving-v1 for scene_direction and masked-refinement-v1 for
masked_refinement. The plan must require human approval. Never propose arbitrary workflow
graphs, copyrighted artist imitation, text, logos, or changes listed in the brief's avoid list.
""".strip()


class AgentRunner(Protocol):
    def run_sync(self, prompt: str) -> Any: ...


class PydanticAIPlanner:
    """Structured model-backed planning behind the same synchronous Planner port."""

    def __init__(self, model: str | None = None, *, runner: AgentRunner | None = None) -> None:
        if runner is None and model is None:
            raise ValueError("A PydanticAI model name or test runner is required")
        self.runner = runner or Agent(
            model,
            output_type=RunPlan,
            instructions=PLANNER_INSTRUCTIONS,
            retries=2,
        )

    def create_plan(self, brief: ArtBrief) -> RunPlan:
        result = self.runner.run_sync(
            "Create a reviewable run plan from this validated art brief:\n"
            f"{brief.model_dump_json(indent=2)}"
        )
        plan = RunPlan.model_validate(result.output)
        recipe_id = (
            "masked-refinement-v1"
            if brief.task_type == "masked_refinement"
            else "composition-preserving-v1"
        )
        directions = [
            direction.model_copy(update={"recipe_id": recipe_id})
            for direction in plan.directions[: brief.variant_count]
        ]
        if len(directions) != brief.variant_count:
            raise ValueError(
                f"Planner returned {len(directions)} directions; expected {brief.variant_count}"
            )
        return plan.model_copy(
            update={
                "project_name": brief.project_name,
                "approval_required": True,
                "directions": directions,
                "preserved_constraints": list(brief.preserve),
                "prohibited_changes": list(brief.avoid),
            }
        )
