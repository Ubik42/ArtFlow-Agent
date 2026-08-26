from __future__ import annotations

import hashlib
import json
from typing import Literal, cast

from pydantic import BaseModel, Field, model_validator

from .contracts import (
    ProviderCapabilityManifest,
    RouteDecision,
    RouteExecutionIntent,
)
from .contracts.execution import ProviderSelection, RejectedProviderAlternative
from .contracts.provider import (
    ControlKind,
    EvaluationEvidenceKind,
    PrivacyClass,
    TaskKind,
)
from .scene_packages import ScenePackagePreview


class RoutePolicyError(RuntimeError):
    """Raised when no provider can satisfy the normalized scene task."""


class ProviderRouteCandidate(BaseModel):
    manifest: ProviderCapabilityManifest
    model_id: str
    availability: Literal["supported", "unsupported", "unknown"]
    estimated_cost_usd: float = Field(ge=0)


class RoutePolicyRequest(BaseModel):
    decision_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    task: TaskKind = "scene_direction"
    privacy_ceiling: PrivacyClass = "local_only"
    max_cost_usd: float = Field(default=0, ge=0)
    output_count: int = Field(default=1, ge=1, le=8)
    output_width: int | None = Field(default=None, ge=64, le=8192)
    output_height: int | None = Field(default=None, ge=64, le=8192)
    prefer_local: bool = True

    @model_validator(mode="after")
    def require_complete_output_size(self) -> RoutePolicyRequest:
        if (self.output_width is None) != (self.output_height is None):
            raise ValueError("output_width and output_height must be supplied together")
        return self


class RoutePolicyResult(BaseModel):
    decision: RouteDecision
    eligible_count: int = Field(ge=1)
    evaluated_count: int = Field(ge=1)


def route_scene_package(
    preview: ScenePackagePreview,
    candidates: list[ProviderRouteCandidate],
    request: RoutePolicyRequest,
) -> RoutePolicyResult:
    if not candidates:
        raise RoutePolicyError("At least one provider candidate is required")
    keys = [(item.manifest.provider_id, item.model_id) for item in candidates]
    if len(keys) != len(set(keys)):
        raise RoutePolicyError("Provider route candidates must be unique")

    required_controls = _required_controls(preview, request.task)
    execution_intent = RouteExecutionIntent(
        required_controls=required_controls,
        evaluation_evidence=_evaluation_evidence(preview),
        output_count=request.output_count,
        width=request.output_width or preview.package.camera.width,
        height=request.output_height or preview.package.camera.height,
        delivery_format=preview.package.delivery.file_format,
        intent_sha256=_intent_sha256(preview),
    )
    eligible: list[tuple[ProviderRouteCandidate, ProviderSelection]] = []
    rejected: list[RejectedProviderAlternative] = []
    for candidate in candidates:
        selection = _selection(candidate)
        reasons = _rejection_reasons(candidate, request, required_controls)
        if reasons:
            rejected.append(
                RejectedProviderAlternative(**selection.model_dump(), reasons=reasons)
            )
        else:
            eligible.append((candidate, selection))
    if not eligible:
        reason_codes = sorted({reason for item in rejected for reason in item.reasons})
        raise RoutePolicyError(
            "No provider satisfies the normalized task: " + ", ".join(reason_codes)
        )

    eligible.sort(key=lambda item: _rank(item[0], request))
    chosen_candidate, selected = eligible[0]
    for candidate, alternative in eligible[1:]:
        reasons = ["lower_deterministic_policy_rank"]
        if candidate.manifest.privacy_class != chosen_candidate.manifest.privacy_class:
            reasons.append("higher_privacy_exposure")
        if candidate.estimated_cost_usd > chosen_candidate.estimated_cost_usd:
            reasons.append("higher_estimated_cost")
        rejected.append(
            RejectedProviderAlternative(**alternative.model_dump(), reasons=reasons)
        )

    decision = RouteDecision(
        decision_id=request.decision_id,
        scene_package_id=preview.package.package_id,
        scene_package_sha256=preview.archive_sha256,
        task=request.task,
        selected=selected,
        rejected=rejected,
        execution_intent=execution_intent,
        privacy_ceiling=request.privacy_ceiling,
        max_cost_usd=request.max_cost_usd,
        requires_explicit_approval=selected.execution_kind != "local",
        rationale=(
            f"Selected {selected.provider_id}/{selected.model_id} from "
            f"{len(eligible)} compatible routes using deterministic privacy, locality and cost rank."
        ),
    )
    return RoutePolicyResult(
        decision=decision,
        eligible_count=len(eligible),
        evaluated_count=len(candidates),
    )


def _required_controls(
    preview: ScenePackagePreview, task: TaskKind
) -> list[ControlKind]:
    controls: list[ControlKind] = ["reference_image"]
    kinds = {item.kind for item in preview.package.passes}
    if task == "masked_refinement" and "editable_mask" in kinds:
        controls.append("mask")
    return controls


def _evaluation_evidence(preview: ScenePackagePreview) -> list[EvaluationEvidenceKind]:
    kinds = {item.kind for item in preview.package.passes}
    return [
        cast(EvaluationEvidenceKind, kind)
        for kind in ("depth", "world_normal", "object_id", "protected_mask")
        if kind in kinds
    ]


def _intent_sha256(preview: ScenePackagePreview) -> str:
    payload = preview.package.art_intent.model_dump(mode="json")
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _selection(candidate: ProviderRouteCandidate) -> ProviderSelection:
    manifest = candidate.manifest
    model = next((item for item in manifest.models if item.model_id == candidate.model_id), None)
    if model is None:
        raise RoutePolicyError(
            f"Provider {manifest.provider_id} does not declare model {candidate.model_id}"
        )
    return ProviderSelection(
        provider_id=manifest.provider_id,
        model_id=model.model_id,
        execution_kind=manifest.execution_kind,
        privacy_class=manifest.privacy_class,
        cost_class=manifest.cost_class,
    )


def _rejection_reasons(
    candidate: ProviderRouteCandidate,
    request: RoutePolicyRequest,
    required_controls: list[ControlKind],
) -> list[str]:
    if candidate.availability != "supported":
        return [f"availability_{candidate.availability}"]
    model = next(
        (item for item in candidate.manifest.models if item.model_id == candidate.model_id),
        None,
    )
    if model is None:
        raise RoutePolicyError(
            f"Provider {candidate.manifest.provider_id} does not declare model {candidate.model_id}"
        )
    reasons: list[str] = []
    if request.task not in model.tasks:
        reasons.append("task_unsupported")
    missing = sorted(set(required_controls) - set(model.controls))
    reasons.extend(f"control_unsupported:{control}" for control in missing)
    if _privacy_rank(candidate.manifest.privacy_class) > _privacy_rank(request.privacy_ceiling):
        reasons.append("privacy_ceiling_exceeded")
    if candidate.estimated_cost_usd > request.max_cost_usd:
        reasons.append("cost_ceiling_exceeded")
    return reasons


def _rank(
    candidate: ProviderRouteCandidate,
    request: RoutePolicyRequest,
) -> tuple[int, float, str, str]:
    local_rank = 0 if candidate.manifest.execution_kind == "local" else 1
    if not request.prefer_local:
        local_rank = 0
    return (
        local_rank,
        candidate.estimated_cost_usd,
        candidate.manifest.provider_id,
        candidate.model_id,
    )


def _privacy_rank(value: PrivacyClass) -> int:
    return {"local_only": 0, "provider_processed": 1, "provider_retained": 2}[value]
