from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .scene_correction_work import file_sha256, resolve_current_correction_receipt
from .scene_disposition import (
    SceneVariantPublishReceipt,
    SceneVariantPublishRequest,
    canonical_sha256,
    compile_publish_request,
)
from .scene_variant_lifecycle import (
    SceneVariantPublishRecord,
    SceneVariantReviewRecord,
)
from .scene_variant_review import (
    SceneVariantReviewReceipt,
    SceneVariantReviewRequest,
    compile_scene_variant_lineage,
    compile_scene_variant_review_request,
)

if TYPE_CHECKING:
    from .agent_runtime import AgentRunState


def compile_current_publish_request(
    project_root: Path, state: AgentRunState
) -> SceneVariantPublishRequest:
    adoption = state.scene_candidate_adoption
    evaluation = state.scene_candidate_evaluation
    intake = state.scene_correction_intake
    work = state.scene_correction_work
    scene = state.scene
    if any(item is None for item in (adoption, evaluation, intake, work, scene)):
        raise ValueError("current publish requires an adopted corrected candidate")
    decision = adoption.decision
    corrected = evaluation.corrected_evaluation
    if corrected.status != "accepted" or corrected.failed_domains:
        raise ValueError("current publish requires an accepted corrected evaluation")
    if decision.evaluation_sha256 != corrected.evaluation_sha256:
        raise ValueError("current adoption references another evaluation")
    _, correction_receipt = resolve_current_correction_receipt(project_root, state)
    relative_candidate = decision.candidate_scene.removeprefix("/Game/")
    candidate = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / f"{relative_candidate}.umap"
    ).resolve()
    candidate_root = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlow/Sessions"
    ).resolve()
    try:
        candidate.relative_to(candidate_root)
    except ValueError as exc:
        raise ValueError("current candidate escaped the Session namespace") from exc
    source = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlowDemo.umap"
    ).resolve()
    if (
        not candidate.is_file()
        or file_sha256(candidate) != decision.candidate_level_sha256
        or not source.is_file()
        or file_sha256(source) != decision.source_level_sha256
        or work.outcome_sha256 != decision.execution_receipt_sha256
        or correction_receipt.candidate_level_sha256
        != decision.candidate_level_sha256
    ):
        raise ValueError("current candidate or source bytes changed after adoption")
    editable = next(
        actor for actor in scene.digital_twin.actors if actor.label == "Editable_Form"
    )
    protected = next(
        actor for actor in scene.digital_twin.actors if actor.label == "Protected_Blockout"
    )
    if len(editable.material_slots) != 1:
        raise ValueError("current editable material identity is ambiguous")
    transform = protected.transform
    protected_publish_fingerprint = canonical_sha256(
        {
            "label": protected.label,
            "class": protected.class_path,
            "location": [
                transform.location.x,
                transform.location.y,
                transform.location.z,
            ],
            "rotation": [
                transform.rotation.roll,
                transform.rotation.pitch,
                transform.rotation.yaw,
            ],
            "scale": [
                transform.scale.x,
                transform.scale.y,
                transform.scale.z,
            ],
            "tags": sorted(protected.tags),
            "materials": [slot.material_path for slot in protected.material_slots],
        }
    )
    return compile_publish_request(
        decision,
        protected_state_sha256=protected_publish_fingerprint,
        material_path=editable.material_slots[0].material_path,
        instance_count=intake.evaluation_input.generated_instance_count_after,
    )


def validate_current_publish_receipt(
    project_root: Path,
    state: AgentRunState,
    receipt: SceneVariantPublishReceipt,
) -> SceneVariantPublishRecord | None:
    request = compile_current_publish_request(project_root, state)
    decision = request.decision
    if (
        receipt.request_id != request.request_id
        or receipt.request_sha256 != request.request_sha256
        or receipt.decision_sha256 != decision.decision_sha256
        or receipt.candidate_scene != decision.candidate_scene
        or receipt.candidate_level_sha256 != decision.candidate_level_sha256
        or receipt.published_scene != decision.published_scene
        or receipt.source_level_sha256_after != decision.source_level_sha256
        or receipt.protected_state_sha256
        != request.expected_protected_state_sha256
        or receipt.material_path != request.expected_material_path
        or receipt.generated_instance_count != request.expected_instance_count
    ):
        raise ValueError("publish receipt references another current candidate")
    published = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / f"{receipt.published_scene.removeprefix('/Game/')}.umap"
    ).resolve()
    published_root = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlow/Published"
    ).resolve()
    try:
        published.relative_to(published_root)
    except ValueError as exc:
        raise ValueError("published receipt escaped the registered namespace") from exc
    if not published.is_file() or file_sha256(published) != receipt.published_level_sha256:
        raise ValueError("published level bytes do not match the Unreal receipt")
    if receipt.status != "reconciled":
        return None
    return SceneVariantPublishRecord(request=request, receipt=receipt)


def compile_current_review_request(state: AgentRunState) -> SceneVariantReviewRequest:
    publication = state.scene_variant_publication
    if publication is None:
        raise ValueError("current review requires a reconciled publication")
    return compile_scene_variant_review_request(
        publication.request, publication.receipt
    )


def validate_current_review_receipt(
    state: AgentRunState,
    receipt: SceneVariantReviewReceipt,
) -> SceneVariantReviewRecord | None:
    publication = state.scene_variant_publication
    evaluation = state.scene_candidate_evaluation
    if publication is None or evaluation is None:
        raise ValueError("current review requires publication and evaluation")
    request = compile_current_review_request(state)
    if (
        receipt.review_id != request.review_id
        or receipt.review_sha256 != request.review_sha256
        or receipt.published_scene != request.published_scene
        or receipt.published_level_sha256 != request.published_level_sha256
        or receipt.source_level_sha256_after != request.source_level_sha256
        or receipt.protected_state_sha256
        != request.expected_protected_state_sha256
        or receipt.material_path != request.expected_material_path
        or receipt.generated_instance_count != request.expected_instance_count
    ):
        raise ValueError("review receipt references another current publication")
    if receipt.status != "reconciled":
        return None
    lineage = compile_scene_variant_lineage(
        failed=evaluation.failed_evaluation,
        corrected=evaluation.corrected_evaluation,
        publish_request=publication.request,
        publish_receipt=publication.receipt,
        review_request=request,
        review_receipt=receipt,
    )
    return SceneVariantReviewRecord(
        request=request,
        receipt=receipt,
        lineage=lineage,
    )
