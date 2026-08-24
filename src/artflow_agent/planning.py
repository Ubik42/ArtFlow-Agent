from __future__ import annotations

from typing import Protocol

from .domain import ArtBrief, RunPlan, VariantDirection


class Planner(Protocol):
    def create_plan(self, brief: ArtBrief) -> RunPlan: ...


DEFAULT_DIRECTIONS = (
    ("cold-storm", "Cold light before a storm", "cool palette, heavy clouds, crisp silhouette"),
    ("warm-ruins", "Warm sunset over ancient ruins", "warm key light, long shadows, dusty air"),
    ("ritual-contrast", "High-contrast mysterious ritual", "dark ambient light, focused emissive accents"),
)


class DeterministicPlanner:
    """Safe placeholder that keeps the application runnable before LLM integration."""

    def create_plan(self, brief: ArtBrief) -> RunPlan:
        directions = [
            VariantDirection(
                name=name,
                visual_goal=goal,
                prompt_delta=delta,
                recipe_id="composition-preserving-v1",
            )
            for name, goal, delta in DEFAULT_DIRECTIONS[: brief.variant_count]
        ]
        return RunPlan(
            project_name=brief.project_name,
            directions=directions,
            preserved_constraints=brief.preserve,
            prohibited_changes=brief.avoid,
        )

