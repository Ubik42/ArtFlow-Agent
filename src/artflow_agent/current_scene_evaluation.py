from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .scene_session import DOMAIN_ORDER, SceneDomain

if TYPE_CHECKING:
    from .agent_runtime import AgentRunState


SHA256 = r"^[a-f0-9]{64}$"


class UnrealCandidateExecutionReceipt(BaseModel):
    """Project-owned receipt emitted by the registered Unreal candidate executor."""

    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-session-candidate-execution-receipt/1"]
    plan_id: str
    plan_sha256: str = Field(pattern=SHA256)
    stage_request_sha256: str = Field(pattern=SHA256)
    source_scene: str
    source_level_sha256_before: str = Field(pattern=SHA256)
    source_level_sha256_after: str = Field(pattern=SHA256)
    source_level_unchanged: bool
    candidate_scene: str
    candidate_level_sha256: str = Field(pattern=SHA256)
    generated_instance_count: int = Field(ge=0, le=10_000)
    reconciled: bool
    candidate_beauty_path: str
    candidate_beauty_sha256: str = Field(pattern=SHA256)
    completed_at: datetime


class CurrentCandidateEvaluationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-current-candidate-evaluation-input/1"] = (
        "artflow-current-candidate-evaluation-input/1"
    )
    input_sha256: str = Field(pattern=SHA256)
    run_id: str
    session_sha256: str = Field(pattern=SHA256)
    work_sha256: str = Field(pattern=SHA256)
    outcome_sha256: str = Field(pattern=SHA256)
    plan_sha256: str = Field(pattern=SHA256)
    stage_request_sha256: str = Field(pattern=SHA256)
    scene_package_sha256: str = Field(pattern=SHA256)
    source_scene: str
    candidate_scene: str
    source_level_sha256: str = Field(pattern=SHA256)
    candidate_level_sha256: str = Field(pattern=SHA256)
    source_beauty_sha256: str = Field(pattern=SHA256)
    candidate_beauty_sha256: str = Field(pattern=SHA256)
    camera_width: int = Field(ge=1)
    camera_height: int = Field(ge=1)
    candidate_width: int = Field(ge=1)
    candidate_height: int = Field(ge=1)
    generated_instance_count: int = Field(ge=0, le=10_000)
    maximum_generated_instances: int = Field(ge=0, le=10_000)
    registered_receipt: str

    @model_validator(mode="after")
    def verify_identity(self) -> CurrentCandidateEvaluationInput:
        payload = self.model_dump(mode="json", exclude={"schema_id", "input_sha256"})
        if self.input_sha256 != canonical_sha256(payload):
            raise ValueError("current candidate evaluation input hash is invalid")
        return self


class CurrentCandidateTechnicalCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: Literal[
        "receipt_identity",
        "source_invariants",
        "candidate_namespace",
        "instance_budget",
        "same_camera_rerender",
        "rerender_content",
    ]
    domain: SceneDomain
    status: Literal["passed", "failed"]
    reason: str = Field(min_length=3, max_length=300)
    evidence_sha256: str = Field(pattern=SHA256)


class CurrentCandidateTechnicalEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-current-candidate-technical-evaluation/1"] = (
        "artflow-current-candidate-technical-evaluation/1"
    )
    evaluation_id: str
    evaluation_sha256: str = Field(pattern=SHA256)
    evaluator_id: Literal["current-session-technical-judge-v1"] = (
        "current-session-technical-judge-v1"
    )
    input_sha256: str = Field(pattern=SHA256)
    checks: list[CurrentCandidateTechnicalCheck] = Field(min_length=6, max_length=6)
    failed_domains: list[SceneDomain]
    status: Literal["eligible_for_visual_review", "rejected"]

    @model_validator(mode="after")
    def verify_evaluation(self) -> CurrentCandidateTechnicalEvaluation:
        ordered_failed = [
            domain
            for domain in DOMAIN_ORDER
            if any(check.domain == domain and check.status == "failed" for check in self.checks)
        ]
        if self.failed_domains != ordered_failed:
            raise ValueError("technical evaluation failed domains do not match checks")
        expected_status = "rejected" if ordered_failed else "eligible_for_visual_review"
        if self.status != expected_status:
            raise ValueError("technical evaluation status does not match checks")
        payload = self.model_dump(
            mode="json", exclude={"schema_id", "evaluation_id", "evaluation_sha256"}
        )
        expected = canonical_sha256(payload)
        if self.evaluation_sha256 != expected:
            raise ValueError("technical evaluation hash is invalid")
        if self.evaluation_id != f"current-technical-evaluation-{expected[:12]}":
            raise ValueError("technical evaluation id is invalid")
        return self


class CurrentCandidateEvaluationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_input: CurrentCandidateEvaluationInput
    technical_evaluation: CurrentCandidateTechnicalEvaluation

    @model_validator(mode="after")
    def verify_chain(self) -> CurrentCandidateEvaluationRecord:
        if self.technical_evaluation.input_sha256 != self.evaluation_input.input_sha256:
            raise ValueError("technical evaluation references another current candidate input")
        return self


def evaluate_current_candidate(
    project_root: Path, state: AgentRunState
) -> CurrentCandidateEvaluationRecord:
    if state.scene is None or not state.scene_sessions:
        raise ValueError("current candidate evaluation requires a Scene Session")
    work = state.scene_candidate_work
    if work is None or work.status != "succeeded" or work.outcome_sha256 is None:
        raise ValueError("current candidate evaluation requires succeeded Unreal work")

    definition = work.definition
    plan = definition.candidate_plan
    receipt_path = (
        project_root
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Saved"
        / "ArtFlowSceneBridge"
        / "SceneCandidates"
        / plan.plan_id
        / "candidate-execution-receipt.json"
    ).resolve()
    if not receipt_path.is_file():
        raise ValueError("registered Unreal candidate receipt is unavailable")
    outcome_sha256 = file_sha256(receipt_path)
    if outcome_sha256 != work.outcome_sha256:
        raise ValueError("registered Unreal receipt does not match the current work outcome")
    receipt = UnrealCandidateExecutionReceipt.model_validate_json(
        receipt_path.read_text(encoding="utf-8-sig")
    )
    if (
        receipt.plan_id != plan.plan_id
        or receipt.plan_sha256 != plan.plan_sha256
        or receipt.stage_request_sha256 != definition.stage_request.request_sha256
        or receipt.source_scene != plan.source_scene
    ):
        raise ValueError("registered Unreal receipt references another candidate plan")

    candidate_root = receipt_path.parent.resolve()
    candidate_beauty = Path(receipt.candidate_beauty_path).resolve()
    try:
        candidate_beauty.relative_to(candidate_root)
    except ValueError as exc:
        raise ValueError("registered candidate rerender escaped its work directory") from exc
    if not candidate_beauty.is_file():
        raise ValueError("registered candidate rerender is unavailable")
    with Image.open(candidate_beauty) as image:
        candidate_width, candidate_height = image.size

    source_beauty = next(
        item for item in state.scene.artifacts if item.path == "passes/beauty.png"
    )
    pcg_limits = [
        operation.max_generated_instances
        for operation in plan.operations
        if operation.domain == "pcg"
    ]
    maximum_generated_instances = pcg_limits[0] if pcg_limits else 0
    package = state.scene.package
    input_payload = {
        "run_id": state.run_id,
        "session_sha256": definition.session_sha256,
        "work_sha256": definition.work_sha256,
        "outcome_sha256": outcome_sha256,
        "plan_sha256": plan.plan_sha256,
        "stage_request_sha256": definition.stage_request.request_sha256,
        "scene_package_sha256": plan.scene_package_sha256,
        "source_scene": plan.source_scene,
        "candidate_scene": receipt.candidate_scene,
        "source_level_sha256": receipt.source_level_sha256_before,
        "candidate_level_sha256": receipt.candidate_level_sha256,
        "source_beauty_sha256": source_beauty.sha256,
        "candidate_beauty_sha256": receipt.candidate_beauty_sha256,
        "camera_width": package.camera.width,
        "camera_height": package.camera.height,
        "candidate_width": candidate_width,
        "candidate_height": candidate_height,
        "generated_instance_count": receipt.generated_instance_count,
        "maximum_generated_instances": maximum_generated_instances,
        "registered_receipt": receipt_path.relative_to(project_root).as_posix(),
    }
    evaluation_input = CurrentCandidateEvaluationInput(
        input_sha256=canonical_sha256(input_payload), **input_payload
    )

    check_values = [
        (
            "receipt_identity",
            "image",
            outcome_sha256 == work.outcome_sha256,
            "工作结果、回执与候选计划身份一致",
        ),
        (
            "source_invariants",
            "lighting",
            receipt.source_level_unchanged
            and receipt.source_level_sha256_before == receipt.source_level_sha256_after,
            "源关卡在候选执行前后保持不变",
        ),
        (
            "candidate_namespace",
            "lighting",
            receipt.candidate_scene == plan.candidate_destination,
            "候选关卡位于当前 Session 的隔离命名空间",
        ),
        (
            "instance_budget",
            "pcg",
            maximum_generated_instances > 0
            and 0 < receipt.generated_instance_count <= maximum_generated_instances,
            f"PCG 实例 {receipt.generated_instance_count}/{maximum_generated_instances}",
        ),
        (
            "same_camera_rerender",
            "image",
            (candidate_width, candidate_height) == (package.camera.width, package.camera.height),
            f"同机位回渲尺寸 {candidate_width}×{candidate_height}",
        ),
        (
            "rerender_content",
            "image",
            file_sha256(candidate_beauty) == receipt.candidate_beauty_sha256,
            "候选回渲内容与 Unreal 回执哈希一致",
        ),
    ]
    checks = [
        CurrentCandidateTechnicalCheck(
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
        for check_id, domain, passed, reason in check_values
    ]
    failed_domains = [
        domain
        for domain in DOMAIN_ORDER
        if any(check.domain == domain and check.status == "failed" for check in checks)
    ]
    evaluation_payload = {
        "evaluator_id": "current-session-technical-judge-v1",
        "input_sha256": evaluation_input.input_sha256,
        "checks": [check.model_dump(mode="json") for check in checks],
        "failed_domains": failed_domains,
        "status": "rejected" if failed_domains else "eligible_for_visual_review",
    }
    evaluation_sha256 = canonical_sha256(evaluation_payload)
    technical_evaluation = CurrentCandidateTechnicalEvaluation(
        evaluation_id=f"current-technical-evaluation-{evaluation_sha256[:12]}",
        evaluation_sha256=evaluation_sha256,
        **evaluation_payload,
    )
    return CurrentCandidateEvaluationRecord(
        evaluation_input=evaluation_input,
        technical_evaluation=technical_evaluation,
    )


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
