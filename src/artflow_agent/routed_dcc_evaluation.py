from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .cloth_banner import ClothBannerRequest
from .scene_disposition import (
    SceneCandidateAdoptionDecision,
    canonical_sha256,
    file_sha256,
)
from .scene_session import SceneCandidateDomainEvaluation, SceneDomainFinding
from .scene_variant_lifecycle import SceneCandidateAdoptionRecord

if TYPE_CHECKING:
    from .agent_runtime import AgentRunState


SHA256 = r"^[a-f0-9]{64}$"
VisualDimension = Literal[
    "material_direction",
    "silhouette_readability",
    "scene_attachment",
    "production_readiness",
]
VISUAL_DIMENSIONS: tuple[VisualDimension, ...] = (
    "material_direction",
    "silhouette_readability",
    "scene_attachment",
    "production_readiness",
)


class RoutedDccVisualClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: VisualDimension
    verdict: Literal["passed", "failed", "uncertain"]
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=8, max_length=300)


class RoutedDccVisualObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-routed-dcc-visual-observation/1"] = (
        "artflow-routed-dcc-visual-observation/1"
    )
    observation_id: str = Field(pattern=r"^dcc-visual-[a-f0-9]{12}$")
    observation_sha256: str = Field(pattern=SHA256)
    evaluator_id: Literal["codex-native-multimodal-critic"] = (
        "codex-native-multimodal-critic"
    )
    route_decision_sha256: str = Field(pattern=SHA256)
    candidate_preview_sha256: str = Field(pattern=SHA256)
    claims: list[RoutedDccVisualClaim] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def verify_identity(self) -> RoutedDccVisualObservation:
        if [claim.dimension for claim in self.claims] != list(VISUAL_DIMENSIONS):
            raise ValueError("routed DCC visual claims must follow the registered rubric")
        unsigned = self.model_dump(
            mode="json", exclude={"schema_id", "observation_id", "observation_sha256"}
        )
        digest = canonical_sha256(unsigned)
        if self.observation_sha256 != digest or self.observation_id != f"dcc-visual-{digest[:12]}":
            raise ValueError("routed DCC visual observation fingerprint mismatch")
        return self


class RoutedDccEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-routed-dcc-evaluation-input/1"] = (
        "artflow-routed-dcc-evaluation-input/1"
    )
    input_sha256: str = Field(pattern=SHA256)
    run_id: str
    session_sha256: str = Field(pattern=SHA256)
    scene_package_sha256: str = Field(pattern=SHA256)
    route_decision_sha256: str = Field(pattern=SHA256)
    route_id: Literal["cloth_banner", "damage_variant", "mechanism_shot"]
    work_sha256: str = Field(pattern=SHA256)
    outcome_sha256: str = Field(pattern=SHA256)
    request_sha256: str = Field(pattern=SHA256)
    candidate_scene: str
    candidate_level_sha256: str = Field(pattern=SHA256)
    candidate_preview_sha256: str = Field(pattern=SHA256)
    candidate_width: int = Field(gt=0)
    candidate_height: int = Field(gt=0)
    source_scene: str
    source_level_sha256: str = Field(pattern=SHA256)
    registered_receipt: str

    @model_validator(mode="after")
    def verify_identity(self) -> RoutedDccEvaluationInput:
        unsigned = self.model_dump(mode="json", exclude={"schema_id", "input_sha256"})
        if self.input_sha256 != canonical_sha256(unsigned):
            raise ValueError("routed DCC evaluation input fingerprint mismatch")
        return self


class RoutedDccTechnicalCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: Literal[
        "route_identity",
        "candidate_namespace",
        "source_invariant",
        "geometry_budget",
        "delivery_readiness",
        "preview_content",
    ]
    domain: Literal["image", "material", "asset"]
    status: Literal["passed", "failed"]
    reason: str = Field(min_length=3, max_length=300)
    evidence_sha256: str = Field(pattern=SHA256)


class RoutedDccCandidateEvaluationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-routed-dcc-candidate-evaluation/1"] = (
        "artflow-routed-dcc-candidate-evaluation/1"
    )
    record_id: str = Field(pattern=r"^dcc-evaluation-[a-f0-9]{12}$")
    record_sha256: str = Field(pattern=SHA256)
    evaluation_input: RoutedDccEvaluationInput
    technical_checks: list[RoutedDccTechnicalCheck] = Field(min_length=6, max_length=6)
    visual_observation: RoutedDccVisualObservation
    domain_evaluation: SceneCandidateDomainEvaluation

    @model_validator(mode="after")
    def verify_chain(self) -> RoutedDccCandidateEvaluationRecord:
        evaluation = self.domain_evaluation
        if (
            self.visual_observation.route_decision_sha256
            != self.evaluation_input.route_decision_sha256
            or self.visual_observation.candidate_preview_sha256
            != self.evaluation_input.candidate_preview_sha256
            or evaluation.plan_sha256 != self.evaluation_input.route_decision_sha256
            or evaluation.candidate_scene != self.evaluation_input.candidate_scene
        ):
            raise ValueError("routed DCC evaluation references another candidate")
        unsigned = self.model_dump(
            mode="json", exclude={"schema_id", "record_id", "record_sha256"}
        )
        digest = canonical_sha256(unsigned)
        if self.record_sha256 != digest or self.record_id != f"dcc-evaluation-{digest[:12]}":
            raise ValueError("routed DCC evaluation record fingerprint mismatch")
        return self


class UnrealClothBannerReceipt(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["artflow-unreal-cloth-banner-receipt/1"]
    request_sha256: str = Field(pattern=SHA256)
    comfy_receipt_sha256: str = Field(pattern=SHA256)
    blender_receipt_sha256: str = Field(pattern=SHA256)
    status: Literal["reconciled"]
    source_candidate_scene_path: str
    candidate_scene_path: str
    triangle_count: int = Field(gt=0)
    material_slot_count: int = Field(ge=0)
    convex_collision_count: int = Field(ge=0)
    source_candidate_sha256_before: str = Field(pattern=SHA256)
    source_candidate_sha256_after: str = Field(pattern=SHA256)
    screenshot_path: str
    screenshot_sha256: str = Field(pattern=SHA256)
    receipt_sha256: str = Field(pattern=SHA256)

    @model_validator(mode="after")
    def verify_identity(self) -> UnrealClothBannerReceipt:
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("Unreal cloth-banner receipt fingerprint mismatch")
        return self


def seal_routed_dcc_visual_observation(
    *,
    route_decision_sha256: str,
    candidate_preview_sha256: str,
    claims: list[dict[str, object]],
) -> RoutedDccVisualObservation:
    payload = {
        "evaluator_id": "codex-native-multimodal-critic",
        "route_decision_sha256": route_decision_sha256,
        "candidate_preview_sha256": candidate_preview_sha256,
        "claims": claims,
    }
    digest = canonical_sha256(payload)
    return RoutedDccVisualObservation(
        observation_id=f"dcc-visual-{digest[:12]}",
        observation_sha256=digest,
        **payload,
    )


def _artifact(root: Path, relative: str, expected_sha256: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("registered routed DCC artifact escaped the project root") from exc
    if not path.is_file() or file_sha256(path) != expected_sha256:
        raise ValueError(f"registered routed DCC artifact changed: {relative}")
    return path


def _registered_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("registered routed DCC path escaped the project root") from exc
    if not path.is_file():
        raise ValueError(f"registered routed DCC artifact is unavailable: {relative}")
    return path


def evaluate_routed_dcc_candidate(
    project_root: Path,
    state: AgentRunState,
    observation: RoutedDccVisualObservation,
) -> RoutedDccCandidateEvaluationRecord:
    work = state.scene_dcc_work
    scene = state.scene
    session = state.scene_sessions[-1] if state.scene_sessions else None
    if work is None or work.status != "succeeded" or work.outcome_sha256 is None:
        raise ValueError("routed DCC evaluation requires succeeded DCC work")
    if scene is None or session is None:
        raise ValueError("routed DCC evaluation requires a current Scene Session")
    definition = work.definition
    decision = definition.route_decision
    if decision is None or decision.selected_route_id != "cloth_banner":
        raise ValueError("current routed evaluator supports the selected cloth-banner route")
    if (
        observation.route_decision_sha256 != decision.decision_sha256
        or observation.candidate_preview_sha256
        != definition.cloth_banner_unreal_preview_sha256
    ):
        raise ValueError("visual observation references another routed candidate")

    request_path = _registered_path(
        project_root,
        "artifacts/goal/m57-s1-cloth-banner/cloth-banner-request.json",
    )
    receipt_path = _registered_path(
        project_root,
        "artifacts/goal/m57-s1-cloth-banner/unreal-cloth-banner-receipt.json",
    )
    request = ClothBannerRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    receipt = UnrealClothBannerReceipt.model_validate_json(
        receipt_path.read_text(encoding="utf-8")
    )
    if (
        request.request_sha256 != definition.cloth_banner_request_sha256
        or receipt.receipt_sha256 != definition.unreal_cloth_banner_receipt_sha256
    ):
        raise ValueError("registered routed DCC contract identity changed")
    preview = _artifact(
        project_root,
        f"artifacts/goal/m57-s1-cloth-banner/{receipt.screenshot_path}",
        receipt.screenshot_sha256,
    )
    candidate = _registered_path(
        project_root,
        f"integrations/unreal/ArtFlowBridgeHost/Content/{receipt.candidate_scene_path.removeprefix('/Game/')}.umap",
    )
    source = project_root / "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlowDemo.umap"
    if not source.is_file():
        raise ValueError("registered source Unreal level is unavailable")
    with Image.open(preview) as image:
        width, height = image.size

    input_payload = {
        "run_id": state.run_id,
        "session_sha256": session.session_sha256,
        "scene_package_sha256": scene.archive_sha256,
        "route_decision_sha256": decision.decision_sha256,
        "route_id": decision.selected_route_id,
        "work_sha256": definition.work_sha256,
        "outcome_sha256": work.outcome_sha256,
        "request_sha256": request.request_sha256,
        "candidate_scene": receipt.candidate_scene_path,
        "candidate_level_sha256": file_sha256(candidate),
        "candidate_preview_sha256": file_sha256(preview),
        "candidate_width": width,
        "candidate_height": height,
        "source_scene": scene.package.provenance.scene_name,
        "source_level_sha256": file_sha256(source),
        "registered_receipt": receipt_path.relative_to(project_root).as_posix(),
    }
    evaluation_input = RoutedDccEvaluationInput(
        input_sha256=canonical_sha256(input_payload), **input_payload
    )
    check_values = [
        (
            "route_identity",
            "asset",
            receipt.receipt_sha256 == work.outcome_sha256
            and receipt.request_sha256 == request.request_sha256
            and receipt.comfy_receipt_sha256 == definition.comfy_banner_texture_receipt_sha256
            and receipt.blender_receipt_sha256 == definition.blender_cloth_banner_receipt_sha256,
            "路线决策、工作结果和三宿主回执身份一致",
        ),
        (
            "candidate_namespace",
            "asset",
            receipt.candidate_scene_path == definition.candidate_scene_path
            and receipt.candidate_scene_path.startswith(
                f"/Game/ArtFlow/Sessions/{session.session_id.replace('scene-session-', 'AF_')}/Candidates/"
            ),
            "Unreal 候选位于当前 Session 的隔离目录",
        ),
        (
            "source_invariant",
            "asset",
            receipt.source_candidate_sha256_before
            == receipt.source_candidate_sha256_after
            == request.source_candidate_sha256,
            "上游候选在旗帜回流前后保持不变",
        ),
        (
            "geometry_budget",
            "asset",
            receipt.triangle_count <= request.triangle_budget,
            f"旗帜三角面 {receipt.triangle_count}/{request.triangle_budget}",
        ),
        (
            "delivery_readiness",
            "material",
            receipt.material_slot_count == 1 and receipt.convex_collision_count >= 1,
            f"材质槽 {receipt.material_slot_count}；凸碰撞体 {receipt.convex_collision_count}",
        ),
        (
            "preview_content",
            "image",
            file_sha256(preview) == receipt.screenshot_sha256,
            f"候选预览 {width}×{height} 与 Unreal 回执一致",
        ),
    ]
    checks = [
        RoutedDccTechnicalCheck(
            check_id=check_id,
            domain=domain,
            status="passed" if passed else "failed",
            reason=reason,
            evidence_sha256=canonical_sha256(
                {
                    "input_sha256": evaluation_input.input_sha256,
                    "check_id": check_id,
                    "passed": passed,
                    "reason": reason,
                }
            ),
        )
        for check_id, domain, passed, reason in check_values
    ]
    claim_by_dimension = {claim.dimension: claim for claim in observation.claims}
    domains = (
        (
            "image",
            ("silhouette_readability", "scene_attachment"),
        ),
        (
            "material",
            ("material_direction", "production_readiness"),
        ),
        (
            "asset",
            ("silhouette_readability", "scene_attachment", "production_readiness"),
        ),
    )
    findings: list[SceneDomainFinding] = []
    for domain, dimensions in domains:
        domain_checks = [check for check in checks if check.domain == domain]
        claims = [claim_by_dimension[dimension] for dimension in dimensions]
        passed = all(check.status == "passed" for check in domain_checks) and all(
            claim.verdict == "passed" for claim in claims
        )
        reason = "；".join(
            [*(check.reason for check in domain_checks), *(claim.rationale for claim in claims)]
        )
        findings.append(
            SceneDomainFinding(
                domain=domain,
                status="passed" if passed else "failed",
                reason=reason,
                evidence_sha256=canonical_sha256(
                    {
                        "input_sha256": evaluation_input.input_sha256,
                        "observation_sha256": observation.observation_sha256,
                        "domain": domain,
                        "technical": [check.evidence_sha256 for check in domain_checks],
                        "claims": [claim.model_dump(mode="json") for claim in claims],
                    }
                ),
            )
        )
    failed_domains = [finding.domain for finding in findings if finding.status == "failed"]
    evaluation_payload = {
        "plan_sha256": decision.decision_sha256,
        "candidate_scene": receipt.candidate_scene_path,
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "failed_domains": failed_domains,
        "status": "correction_required" if failed_domains else "accepted",
    }
    evaluation_sha = canonical_sha256(evaluation_payload)
    domain_evaluation = SceneCandidateDomainEvaluation(
        evaluation_id=f"domain-evaluation-{evaluation_sha[:12]}",
        evaluation_sha256=evaluation_sha,
        **evaluation_payload,
    )
    record_payload = {
        "evaluation_input": evaluation_input.model_dump(mode="json"),
        "technical_checks": [check.model_dump(mode="json") for check in checks],
        "visual_observation": observation.model_dump(mode="json"),
        "domain_evaluation": domain_evaluation.model_dump(mode="json"),
    }
    record_sha = canonical_sha256(record_payload)
    return RoutedDccCandidateEvaluationRecord(
        record_id=f"dcc-evaluation-{record_sha[:12]}",
        record_sha256=record_sha,
        evaluation_input=evaluation_input,
        technical_checks=checks,
        visual_observation=observation,
        domain_evaluation=domain_evaluation,
    )


def compile_routed_dcc_adoption(
    project_root: Path, state: AgentRunState
) -> SceneCandidateAdoptionRecord:
    routed = state.scene_dcc_candidate_evaluation
    work = state.scene_dcc_work
    if routed is None or work is None or state.scene is None:
        raise ValueError("routed DCC adoption requires persisted evaluation")
    evaluation = routed.domain_evaluation
    if evaluation.status != "accepted" or evaluation.failed_domains:
        raise ValueError("only an accepted routed DCC candidate can be adopted")
    input_record = routed.evaluation_input
    if (
        input_record.work_sha256 != work.definition.work_sha256
        or input_record.outcome_sha256 != work.outcome_sha256
    ):
        raise ValueError("routed evaluation references another DCC work item")
    candidate = (
        project_root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / f"{input_record.candidate_scene.removeprefix('/Game/')}.umap"
    ).resolve()
    source = project_root / "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlowDemo.umap"
    if (
        not candidate.is_file()
        or file_sha256(candidate) != input_record.candidate_level_sha256
        or not source.is_file()
        or file_sha256(source) != input_record.source_level_sha256
    ):
        raise ValueError("routed candidate or source bytes changed after evaluation")
    identity_payload = {
        "evaluation_sha256": evaluation.evaluation_sha256,
        "plan_sha256": input_record.route_decision_sha256,
        "execution_receipt_sha256": input_record.outcome_sha256,
        "source_level_sha256": input_record.source_level_sha256,
        "candidate_level_sha256": input_record.candidate_level_sha256,
    }
    content_identity = canonical_sha256(identity_payload)
    session_segment = input_record.candidate_scene.split("/")[4].removeprefix("AF_")
    payload = {
        "action": "publish",
        "orchestrator": "codex",
        "policy_version": "scene-disposition-policy/1",
        "evaluation_sha256": evaluation.evaluation_sha256,
        "plan_sha256": input_record.route_decision_sha256,
        "execution_receipt_sha256": input_record.outcome_sha256,
        "content_identity_sha256": content_identity,
        "source_scene": input_record.source_scene,
        "source_level_sha256": input_record.source_level_sha256,
        "candidate_scene": input_record.candidate_scene,
        "candidate_level_sha256": input_record.candidate_level_sha256,
        "published_scene": f"/Game/ArtFlow/Published/AF_{session_segment}/V_{content_identity[:12]}",
        "rationale": (
            "当前自动选路候选通过内容身份、几何预算、材质碰撞和独立视觉评价；"
            "Codex 采用该精确 Unreal 候选并交给既有版本发布器。"
        ),
    }
    decision_sha = canonical_sha256(payload)
    return SceneCandidateAdoptionRecord(
        decision=SceneCandidateAdoptionDecision(
            decision_id=f"scene-adoption-{decision_sha[:16]}",
            decision_sha256=decision_sha,
            **payload,
        )
    )
