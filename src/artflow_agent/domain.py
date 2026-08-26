from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from .contracts import ApprovalGrant, RouteDecision


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
    comfyui_version: str | None = None
    python_version: str | None = None
    pytorch_version: str | None = None
    device_name: str | None = None
    models: list[str] = Field(default_factory=list)
    model_inventory: dict[str, list[str]] = Field(default_factory=dict)
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


class RecipeTarget(BaseModel):
    node_id: str
    input_name: str


class RecipeSlot(BaseModel):
    """A reviewed value and every workflow input it is allowed to change."""

    name: str
    node_id: str | None = None
    input_name: str | None = None
    targets: list[RecipeTarget] = Field(default_factory=list)
    value_type: Literal["string", "integer", "number", "boolean"]
    required: bool = True
    minimum: int | float | None = None
    maximum: int | float | None = None

    def resolved_targets(self) -> list[RecipeTarget]:
        if self.targets:
            return self.targets
        if self.node_id is not None and self.input_name is not None:
            return [RecipeTarget(node_id=self.node_id, input_name=self.input_name)]
        return []


class RecipeDefinition(BaseModel):
    recipe_id: str
    version: str
    task_type: Literal["scene_direction", "masked_refinement"]
    description: str
    workflow_file: str
    execution_ready: bool = False
    consumed_controls: list[
        Literal[
            "reference_image",
            "mask",
            "depth",
            "world_normal",
            "object_id",
            "multi_turn_edit",
        ]
    ] = Field(default_factory=list)
    required_models: list[str] = Field(default_factory=list)
    required_nodes: list[str] = Field(default_factory=list)
    estimated_vram_mb: int | None = Field(default=None, ge=0)
    slots: list[RecipeSlot]


class QueuedJob(BaseModel):
    prompt_id: str
    client_id: str
    number: int | None = None


class UploadedInput(BaseModel):
    name: str
    subfolder: str = ""
    type: str = "input"


class OutputArtifact(BaseModel):
    filename: str
    subfolder: str = ""
    type: str = "output"
    node_id: str | None = None
    local_path: str | None = None


class EnvironmentFingerprint(BaseModel):
    comfy_url: HttpUrl
    comfyui_version: str | None = None
    python_version: str | None = None
    pytorch_version: str | None = None
    device_name: str | None = None
    vram_mb: int | None = None
    verified_models: list[str]
    verified_nodes: list[str]


class GenerationReceipt(BaseModel):
    prompt_id: str
    recipe_id: str
    recipe_version: str
    workflow_sha256: str
    queued_at: datetime
    completed_at: datetime
    environment: EnvironmentFingerprint | None = None
    resolved_inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: list[OutputArtifact] = Field(default_factory=list)


class Candidate(BaseModel):
    candidate_id: str
    direction_name: str
    image_path: str
    receipt_path: str | None = None


class DirectionRun(BaseModel):
    direction_name: str
    status: Literal["pending", "running", "completed", "failed"] = "pending"
    attempt_count: int = 0
    prompt_id: str | None = None
    receipt_path: str | None = None
    candidates: list[Candidate] = Field(default_factory=list)
    error: str | None = None


class RunEvent(BaseModel):
    event_type: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data: dict[str, Any] = Field(default_factory=dict)


class RunState(BaseModel):
    run_id: str
    brief: ArtBrief
    plan: RunPlan
    status: Literal["awaiting_approval", "approved", "running", "review", "completed", "failed"]
    parent_run_id: str | None = None
    source_candidate_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_at: datetime | None = None
    route_decision: RouteDecision | None = None
    approval_grant: ApprovalGrant | None = None
    direction_runs: list[DirectionRun] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    selected_candidate_id: str | None = None

    def model_post_init(self, __context: Any, /) -> None:
        if not self.direction_runs:
            self.direction_runs = [
                DirectionRun(direction_name=direction.name) for direction in self.plan.directions
            ]


class TrajectoryCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class TrajectoryEvaluation(BaseModel):
    run_id: str
    passed: bool
    checks: list[TrajectoryCheck]


class AssetCheck(BaseModel):
    name: str
    passed: bool
    value: float | str
    threshold: float | str
    detail: str


class CandidateEvaluation(BaseModel):
    candidate_id: str
    passed: bool
    checks: list[AssetCheck]


class VisualCriterion(BaseModel):
    name: Literal["composition", "direction", "coherence", "constraint_safety"]
    score: int = Field(ge=1, le=5)
    rationale: str


class VisualJudgment(BaseModel):
    criteria: list[VisualCriterion]
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    revision_instruction: str


class CandidateVisualEvaluation(BaseModel):
    candidate_id: str
    passed: bool
    overall_score: float
    judgment: VisualJudgment
