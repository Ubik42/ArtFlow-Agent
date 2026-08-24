from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class ArtBrief(BaseModel):
    """User-owned constraints that must survive every generation round."""

    project_name: str = Field(min_length=1, max_length=120)
    task_type: Literal["scene_direction", "masked_refinement"] = "scene_direction"
    source_image: str = Field(min_length=1)
    style_references: list[str] = Field(default_factory=list, max_length=3)
    intent: str = Field(min_length=10, max_length=1200)
    preserve: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    variant_count: int = Field(default=3, ge=1, le=6)


class EnvironmentSnapshot(BaseModel):
    comfy_url: HttpUrl
    reachable: bool
    models: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    vram_mb: int | None = Field(default=None, ge=0)


class VariantDirection(BaseModel):
    name: str
    visual_goal: str
    prompt_delta: str
    recipe_id: str


class RunPlan(BaseModel):
    project_name: str
    approval_required: bool = True
    directions: list[VariantDirection]
    preserved_constraints: list[str] = Field(default_factory=list)
    prohibited_changes: list[str] = Field(default_factory=list)

