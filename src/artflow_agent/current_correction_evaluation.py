from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .current_visual_critic import CurrentCandidateVisualObservation
from .scene_correction_work import (
    file_sha256,
    resolve_current_correction_beauty,
    resolve_current_correction_receipt,
)
from .scene_disposition import (
    DISPOSITION_POLICY_VERSION,
    SceneCandidateAdoptionDecision,
)
from .scene_session import (
    DOMAIN_ORDER,
    SceneCandidateDomainEvaluation,
    SceneDomain,
    SceneDomainFinding,
)
from .scene_variant_lifecycle import (
    SceneCandidateAdoptionRecord,
    SceneCandidateEvaluationRecord,
)

if TYPE_CHECKING:
    from .agent_runtime import AgentRunState


SHA256 = r"^[a-f0-9]{64}$"


class CurrentCorrectionEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-current-correction-evaluation-input/1"] = (
        "artflow-current-correction-evaluation-input/1"
    )
    input_sha256: str = Field(pattern=SHA256)
    run_id: str
    session_sha256: str = Field(pattern=SHA256)
    correction_work_sha256: str = Field(pattern=SHA256)
    correction_outcome_sha256: str = Field(pattern=SHA256)
    prior_evaluation_sha256: str = Field(pattern=SHA256)
    plan_sha256: str = Field(pattern=SHA256)
    candidate_scene: str
    source_level_sha256: str = Field(pattern=SHA256)
    host_candidate_level_sha256: str = Field(pattern=SHA256)
    current_candidate_level_sha256: str = Field(pattern=SHA256)
    source_beauty_sha256: str = Field(pattern=SHA256)
    corrected_beauty_sha256: str = Field(pattern=SHA256)
    preserved_evidence_sha256s: dict[SceneDomain, str]
    protected_state_before: str = Field(pattern=SHA256)
    protected_state_after: str = Field(pattern=SHA256)
    generated_instance_count_before: int = Field(ge=0, le=10_000)
    generated_instance_count_after: int = Field(ge=0, le=10_000)
    intensity_before: float
    intensity_after: float
    temperature_before: float
    temperature_after: float
    key_light_pitch_before: float | None = None
    key_light_pitch_after: float | None = None
    key_light_yaw_before: float | None = None
    key_light_yaw_after: float | None = None
    secondary_intensity_before: float | None = None
    secondary_intensity_after: float | None = None
    secondary_temperature_before: float | None = None
    secondary_temperature_after: float | None = None
    registered_receipt: str

    @model_validator(mode="after")
    def verify_identity(self) -> CurrentCorrectionEvaluationInput:
        payload = self.model_dump(
            mode="json", exclude={"schema_id", "input_sha256"}, exclude_none=True
        )
        if self.input_sha256 != canonical_sha256(payload):
            raise ValueError("current correction evaluation input hash is invalid")
        return self


class CurrentCorrectionTechnicalCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: Literal[
        "receipt_identity",
        "source_invariants",
        "protected_invariants",
        "pcg_preserved",
        "failed_domain_scope",
        "lighting_patch",
        "corrected_rerender",
    ]
    domain: SceneDomain
    status: Literal["passed", "failed"]
    reason: str = Field(min_length=3, max_length=300)
    evidence_sha256: str = Field(pattern=SHA256)


class CurrentCorrectionTechnicalEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-current-correction-technical-evaluation/1"] = (
        "artflow-current-correction-technical-evaluation/1"
    )
    evaluation_id: str
    evaluation_sha256: str = Field(pattern=SHA256)
    evaluator_id: Literal["current-correction-technical-judge-v1"] = (
        "current-correction-technical-judge-v1"
    )
    input_sha256: str = Field(pattern=SHA256)
    checks: list[CurrentCorrectionTechnicalCheck] = Field(min_length=7, max_length=7)
    failed_domains: list[SceneDomain]
    status: Literal["eligible_for_visual_review", "rejected"]

    @model_validator(mode="after")
    def verify_evaluation(self) -> CurrentCorrectionTechnicalEvaluation:
        ordered_failed = [
            domain
            for domain in DOMAIN_ORDER
            if any(check.domain == domain and check.status == "failed" for check in self.checks)
        ]
        if self.failed_domains != ordered_failed:
            raise ValueError("correction technical failed domains do not match checks")
        expected_status = "rejected" if ordered_failed else "eligible_for_visual_review"
        if self.status != expected_status:
            raise ValueError("correction technical status does not match checks")
        payload = self.model_dump(
            mode="json", exclude={"schema_id", "evaluation_id", "evaluation_sha256"}
        )
        expected = canonical_sha256(payload)
        if self.evaluation_sha256 != expected:
            raise ValueError("correction technical evaluation hash is invalid")
        if self.evaluation_id != f"correction-technical-evaluation-{expected[:12]}":
            raise ValueError("correction technical evaluation id is invalid")
        return self


class CurrentCorrectionEvaluationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_input: CurrentCorrectionEvaluationInput
    technical_evaluation: CurrentCorrectionTechnicalEvaluation

    @model_validator(mode="after")
    def verify_chain(self) -> CurrentCorrectionEvaluationRecord:
        if self.technical_evaluation.input_sha256 != self.evaluation_input.input_sha256:
            raise ValueError("correction technical evaluation references another input")
        return self


class CurrentCorrectionDomainVerdictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technical_intake_sha256: str = Field(pattern=SHA256)
    visual_observation: CurrentCandidateVisualObservation
    domain_evaluation: SceneCandidateDomainEvaluation

    @model_validator(mode="after")
    def verify_chain(self) -> CurrentCorrectionDomainVerdictRecord:
        if self.visual_observation.input_sha256 != self.technical_intake_sha256:
            raise ValueError("corrected visual observation references another intake")
        return self


def evaluate_current_correction(
    project_root: Path, state: AgentRunState
) -> CurrentCorrectionEvaluationRecord:
    work = state.scene_correction_work
    original_intake = state.scene_candidate_intake
    original_verdict = state.scene_candidate_visual_verdict
    if (
        work is None
        or work.status != "succeeded"
        or work.outcome_sha256 is None
        or original_intake is None
        or original_verdict is None
        or state.scene is None
        or not state.scene_sessions
    ):
        raise ValueError("correction reevaluation requires the current succeeded correction")
    receipt_path, receipt = resolve_current_correction_receipt(project_root, state)
    beauty = resolve_current_correction_beauty(project_root, state)
    definition = work.definition
    relative_candidate = definition.candidate_scene.removeprefix("/Game/")
    candidate_root = (
        project_root
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Content"
        / "ArtFlow"
        / "Sessions"
    ).resolve()
    candidate_file = (
        project_root
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Content"
        / f"{relative_candidate}.umap"
    ).resolve()
    try:
        candidate_file.relative_to(candidate_root)
    except ValueError as exc:
        raise ValueError("current correction candidate escaped the Session namespace") from exc
    if not candidate_file.is_file():
        raise ValueError("current corrected candidate level is unavailable")
    source_file = (
        project_root
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Content"
        / "ArtFlowDemo.umap"
    ).resolve()
    source_beauty = next(
        item for item in state.scene.artifacts if item.path == "passes/beauty.png"
    )
    input_payload = {
        "run_id": state.run_id,
        "session_sha256": definition.session_sha256,
        "correction_work_sha256": definition.work_sha256,
        "correction_outcome_sha256": work.outcome_sha256,
        "prior_evaluation_sha256": definition.evaluation_sha256,
        "plan_sha256": definition.candidate_plan_sha256,
        "candidate_scene": definition.candidate_scene,
        "source_level_sha256": receipt.source_level_sha256_after,
        "host_candidate_level_sha256": receipt.candidate_level_sha256,
        "current_candidate_level_sha256": file_sha256(candidate_file),
        "source_beauty_sha256": source_beauty.sha256,
        "corrected_beauty_sha256": receipt.corrected_beauty_sha256,
        "preserved_evidence_sha256s": (
            definition.correction_plan.preserved_evidence_sha256s
        ),
        "protected_state_before": receipt.protected_state_before,
        "protected_state_after": receipt.protected_state_after,
        "generated_instance_count_before": receipt.generated_instance_count_before,
        "generated_instance_count_after": receipt.generated_instance_count_after,
        "intensity_before": receipt.intensity_before,
        "intensity_after": receipt.intensity_after,
        "temperature_before": receipt.temperature_before,
        "temperature_after": receipt.temperature_after,
        "key_light_pitch_before": receipt.key_light_pitch_before,
        "key_light_pitch_after": receipt.key_light_pitch_after,
        "key_light_yaw_before": receipt.key_light_yaw_before,
        "key_light_yaw_after": receipt.key_light_yaw_after,
        "secondary_intensity_before": receipt.secondary_intensity_before,
        "secondary_intensity_after": receipt.secondary_intensity_after,
        "secondary_temperature_before": receipt.secondary_temperature_before,
        "secondary_temperature_after": receipt.secondary_temperature_after,
        "registered_receipt": receipt_path.relative_to(project_root).as_posix(),
    }
    input_payload = {key: value for key, value in input_payload.items() if value is not None}
    evaluation_input = CurrentCorrectionEvaluationInput(
        input_sha256=canonical_sha256(input_payload), **input_payload
    )
    plan = definition.correction_plan
    original_candidate_sha = original_intake.evaluation_input.candidate_beauty_sha256
    checks = [
        (
            "receipt_identity",
            "lighting",
            receipt.work_sha256 == definition.work_sha256
            and receipt.evaluation_sha256 == definition.evaluation_sha256
            and receipt.correction_sha256 == plan.correction_sha256
            and receipt.candidate_scene == definition.candidate_scene,
            "纠正工作、父裁决、候选与宿主回执身份一致",
        ),
        (
            "source_invariants",
            "lighting",
            receipt.source_level_unchanged
            and receipt.source_level_sha256_before == receipt.source_level_sha256_after
            and file_sha256(source_file) == receipt.source_level_sha256_after,
            "源关卡在纠正前后及当前磁盘状态保持一致",
        ),
        (
            "protected_invariants",
            "image",
            receipt.protected_state_before == receipt.protected_state_after,
            "受保护结构语义指纹在灯光纠正前后保持一致",
        ),
        (
            "pcg_preserved",
            "pcg",
            receipt.generated_instance_count_before
            == receipt.generated_instance_count_after
            == 12
            and "pcg" in plan.preserved_evidence_sha256s,
            "PCG 实例保持 12→12，原通过证据继续封存",
        ),
        (
            "failed_domain_scope",
            "lighting",
            plan.failed_domains == plan.rerun_domains == ["lighting"]
            and set(plan.preserved_evidence_sha256s) == {"image", "pcg"},
            "纠正只重跑 lighting，并保留 image 与 PCG",
        ),
        (
            "lighting_patch",
            "lighting",
            abs(receipt.intensity_after - plan.lighting_intensity) < 0.001
            and abs(receipt.temperature_after - plan.lighting_temperature_kelvin) < 0.001
            and (
                plan.key_light_pitch_degrees is None
                or (
                    receipt.key_light_pitch_after is not None
                    and receipt.key_light_yaw_after is not None
                    and receipt.secondary_intensity_after is not None
                    and receipt.secondary_temperature_after is not None
                    and abs(
                        receipt.key_light_pitch_after
                        - plan.key_light_pitch_degrees
                    )
                    < 0.001
                    and abs(
                        receipt.key_light_yaw_after - plan.key_light_yaw_degrees
                    )
                    < 0.001
                    and abs(
                        receipt.secondary_intensity_after
                        - plan.secondary_light_intensity
                    )
                    < 0.001
                    and abs(
                        receipt.secondary_temperature_after
                        - plan.secondary_light_temperature_kelvin
                    )
                    < 0.001
                )
            )
            and (
                receipt.intensity_before != receipt.intensity_after
                or receipt.temperature_before != receipt.temperature_after
                or receipt.key_light_pitch_before != receipt.key_light_pitch_after
                or receipt.key_light_yaw_before != receipt.key_light_yaw_after
                or receipt.secondary_intensity_before
                != receipt.secondary_intensity_after
                or receipt.secondary_temperature_before
                != receipt.secondary_temperature_after
            ),
            "注册灯光组参数按类型化补丁发生实际变化",
        ),
        (
            "corrected_rerender",
            "image",
            file_sha256(beauty) == receipt.corrected_beauty_sha256
            and receipt.corrected_beauty_sha256 != original_candidate_sha,
            "同机位纠正回渲内容与宿主哈希一致且不同于原候选",
        ),
    ]
    technical_checks = [
        CurrentCorrectionTechnicalCheck(
            check_id=check_id,
            domain=domain,
            status="passed" if passed else "failed",
            reason=reason,
            evidence_sha256=canonical_sha256(
                {
                    "input_sha256": evaluation_input.input_sha256,
                    "check_id": check_id,
                    "domain": domain,
                    "passed": passed,
                    "reason": reason,
                }
            ),
        )
        for check_id, domain, passed, reason in checks
    ]
    failed_domains = [
        domain
        for domain in DOMAIN_ORDER
        if any(check.domain == domain and check.status == "failed" for check in technical_checks)
    ]
    technical_payload = {
        "evaluator_id": "current-correction-technical-judge-v1",
        "input_sha256": evaluation_input.input_sha256,
        "checks": [check.model_dump(mode="json") for check in technical_checks],
        "failed_domains": failed_domains,
        "status": "rejected" if failed_domains else "eligible_for_visual_review",
    }
    technical_sha = canonical_sha256(technical_payload)
    return CurrentCorrectionEvaluationRecord(
        evaluation_input=evaluation_input,
        technical_evaluation=CurrentCorrectionTechnicalEvaluation(
            evaluation_id=f"correction-technical-evaluation-{technical_sha[:12]}",
            evaluation_sha256=technical_sha,
            **technical_payload,
        ),
    )


def compile_corrected_domain_verdict(
    state: AgentRunState,
    observation: CurrentCandidateVisualObservation,
) -> CurrentCorrectionDomainVerdictRecord:
    intake = state.scene_correction_intake
    original = state.scene_candidate_visual_verdict
    work = state.scene_correction_work
    if intake is None or original is None or work is None:
        raise ValueError("corrected visual verdict requires current correction intake")
    technical = intake.technical_evaluation
    evaluation_input = intake.evaluation_input
    if technical.status != "eligible_for_visual_review" or technical.failed_domains:
        raise ValueError("a rejected correction intake cannot enter visual scoring")
    if (
        observation.input_sha256 != evaluation_input.input_sha256
        or observation.source_beauty_sha256 != evaluation_input.source_beauty_sha256
        or observation.candidate_beauty_sha256
        != evaluation_input.corrected_beauty_sha256
    ):
        raise ValueError("corrected visual observation references another result")
    if observation.recommended_failed_domains not in ([], ["lighting"]):
        raise ValueError("corrected visual observation may classify only lighting")
    claims = {claim.dimension: claim for claim in observation.claims}
    lighting_claims = [claims["lighting_direction"], claims["visual_coherence"]]
    lighting_passed = (
        all(claim.verdict == "passed" for claim in lighting_claims)
        and "lighting" not in observation.recommended_failed_domains
    )
    original_findings = {
        finding.domain: finding for finding in original.domain_evaluation.findings
    }
    findings = [
        original_findings["image"],
        original_findings["pcg"],
        SceneDomainFinding(
            domain="lighting",
            status="passed" if lighting_passed else "failed",
            reason="；".join(claim.rationale for claim in lighting_claims),
            evidence_sha256=canonical_sha256(
                {
                    "technical_evaluation_sha256": technical.evaluation_sha256,
                    "visual_observation_sha256": observation.observation_sha256,
                    "correction_outcome_sha256": evaluation_input.correction_outcome_sha256,
                    "domain": "lighting",
                    "claims": [claim.model_dump(mode="json") for claim in lighting_claims],
                    "hard_gate_precedence": True,
                }
            ),
        ),
    ]
    failed_domains: list[SceneDomain] = [] if lighting_passed else ["lighting"]
    evaluation_payload = {
        "plan_sha256": evaluation_input.plan_sha256,
        "candidate_scene": evaluation_input.candidate_scene,
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "failed_domains": failed_domains,
        "status": "accepted" if lighting_passed else "correction_required",
    }
    evaluation_sha = canonical_sha256(evaluation_payload)
    evaluation = SceneCandidateDomainEvaluation(
        evaluation_id=f"domain-evaluation-{evaluation_sha[:12]}",
        evaluation_sha256=evaluation_sha,
        **evaluation_payload,
    )
    return CurrentCorrectionDomainVerdictRecord(
        technical_intake_sha256=evaluation_input.input_sha256,
        visual_observation=observation,
        domain_evaluation=evaluation,
    )


def compile_current_evaluation_record(state: AgentRunState) -> SceneCandidateEvaluationRecord:
    corrected = state.scene_correction_visual_verdict
    failed = state.scene_candidate_visual_verdict
    parent = state.scene_candidate_work
    if corrected is None or failed is None or parent is None:
        raise ValueError("current lifecycle evaluation requires both candidate verdicts")
    if corrected.domain_evaluation.status != "accepted":
        raise ValueError("current corrected candidate has not passed reevaluation")
    return SceneCandidateEvaluationRecord(
        stage_request=parent.definition.stage_request,
        failed_plan=parent.definition.candidate_plan,
        failed_evaluation=failed.domain_evaluation,
        corrected_plan=parent.definition.candidate_plan,
        corrected_evaluation=corrected.domain_evaluation,
    )


def compile_current_adoption_record(
    project_root: Path, state: AgentRunState
) -> SceneCandidateAdoptionRecord:
    evaluation = state.scene_candidate_evaluation
    work = state.scene_correction_work
    intake = state.scene_correction_intake
    if evaluation is None or work is None or intake is None or state.scene is None:
        raise ValueError("current adoption requires persisted corrected evaluation")
    corrected = evaluation.corrected_evaluation
    plan = evaluation.corrected_plan
    if corrected.status != "accepted" or corrected.failed_domains:
        raise ValueError("only an accepted corrected candidate can be adopted")
    if corrected.evaluation_sha256 != state.scene_correction_visual_verdict.domain_evaluation.evaluation_sha256:
        raise ValueError("persisted evaluation references another corrected verdict")
    receipt_path, receipt = resolve_current_correction_receipt(project_root, state)
    relative_candidate = receipt.candidate_scene.removeprefix("/Game/")
    candidate_file = (
        project_root
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Content"
        / f"{relative_candidate}.umap"
    ).resolve()
    source_file = (
        project_root
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Content"
        / "ArtFlowDemo.umap"
    ).resolve()
    current_candidate_sha = file_sha256(candidate_file)
    if (
        current_candidate_sha
        != intake.evaluation_input.current_candidate_level_sha256
        or file_sha256(source_file) != receipt.source_level_sha256_after
        or file_sha256(receipt_path) != work.outcome_sha256
        or corrected.plan_sha256 != plan.plan_sha256
        or corrected.candidate_scene != plan.candidate_destination
    ):
        raise ValueError("candidate or source bytes changed after corrected evaluation")
    identity_payload = {
        "evaluation_sha256": corrected.evaluation_sha256,
        "plan_sha256": plan.plan_sha256,
        "execution_receipt_sha256": work.outcome_sha256,
        "source_level_sha256": receipt.source_level_sha256_after,
        "candidate_level_sha256": current_candidate_sha,
    }
    content_identity = canonical_sha256(identity_payload)
    session_segment = receipt.candidate_scene.split("/")[4].removeprefix("AF_")
    payload = {
        "action": "publish",
        "orchestrator": "codex",
        "policy_version": DISPOSITION_POLICY_VERSION,
        "evaluation_sha256": corrected.evaluation_sha256,
        "plan_sha256": plan.plan_sha256,
        "execution_receipt_sha256": work.outcome_sha256,
        "content_identity_sha256": content_identity,
        "source_scene": state.scene.package.provenance.scene_name,
        "source_level_sha256": receipt.source_level_sha256_after,
        "candidate_scene": receipt.candidate_scene,
        "candidate_level_sha256": current_candidate_sha,
        "published_scene": (
            f"/Game/ArtFlow/Published/AF_{session_segment}/V_{content_identity[:12]}"
        ),
        "rationale": (
            "当前纠正候选通过独立技术与视觉复评；Codex 采用该内容身份，"
            "保留发布目标但本步骤不执行 Unreal 发布。"
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


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
