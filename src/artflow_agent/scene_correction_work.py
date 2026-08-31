from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .scene_session import SceneDomainCorrectionPlan

if TYPE_CHECKING:
    from .agent_runtime import AgentRunState


SHA256 = r"^[a-f0-9]{64}$"
SceneCorrectionWorkStatus = Literal[
    "queued", "claimed", "executing", "reconciling", "succeeded", "failed"
]
SceneCorrectionProgressStatus = Literal[
    "executing", "reconciling", "succeeded", "failed"
]


class SceneCorrectionWorkDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-correction-work/1"] = (
        "artflow-scene-correction-work/1"
    )
    work_id: str = Field(pattern=r"^scene-correction-[a-f0-9]{12}$")
    work_sha256: str = Field(pattern=SHA256)
    run_id: str
    session_sha256: str = Field(pattern=SHA256)
    parent_work_sha256: str = Field(pattern=SHA256)
    parent_outcome_sha256: str = Field(pattern=SHA256)
    source_level_sha256: str | None = Field(default=None, pattern=SHA256)
    candidate_plan_sha256: str = Field(pattern=SHA256)
    candidate_scene: str
    evaluation_sha256: str = Field(pattern=SHA256)
    correction_plan: SceneDomainCorrectionPlan

    @model_validator(mode="after")
    def verify_identity(self) -> SceneCorrectionWorkDefinition:
        if (
            self.correction_plan.evaluation_sha256 != self.evaluation_sha256
            or self.correction_plan.candidate_scene != self.candidate_scene
        ):
            raise ValueError("correction work plan references another evaluation or candidate")
        payload = self.model_dump(
            mode="json",
            exclude={"schema_id", "work_id", "work_sha256"},
            exclude_none=True,
        )
        expected = canonical_sha256(payload)
        if self.work_sha256 != expected:
            raise ValueError("correction work content hash is invalid")
        if self.work_id != f"scene-correction-{expected[:12]}":
            raise ValueError("correction work id is invalid")
        return self


class SceneCorrectionWorkState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    definition: SceneCorrectionWorkDefinition
    status: SceneCorrectionWorkStatus = "queued"
    worker_id: str | None = None
    outcome_sha256: str | None = Field(default=None, pattern=SHA256)
    message: str | None = Field(default=None, max_length=500)


class SceneCorrectionWorkClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-correction-claim/1"] = (
        "artflow-scene-correction-claim/1"
    )
    work_sha256: str = Field(pattern=SHA256)
    session_sha256: str = Field(pattern=SHA256)
    worker_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")


class SceneCorrectionWorkProgressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-correction-progress/1"] = (
        "artflow-scene-correction-progress/1"
    )
    work_sha256: str = Field(pattern=SHA256)
    worker_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    status: SceneCorrectionProgressStatus
    action_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    outcome_sha256: str | None = Field(default=None, pattern=SHA256)
    message: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_terminal_detail(self) -> SceneCorrectionWorkProgressRequest:
        if self.status == "succeeded" and self.outcome_sha256 is None:
            raise ValueError("succeeded correction work requires an outcome identity")
        if self.status == "failed" and not self.message:
            raise ValueError("failed correction work requires a recovery message")
        return self


class UnrealLightingCorrectionReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-session-lighting-correction-receipt/1"]
    work_id: str
    work_sha256: str = Field(pattern=SHA256)
    evaluation_sha256: str = Field(pattern=SHA256)
    correction_sha256: str = Field(pattern=SHA256)
    candidate_plan_sha256: str = Field(pattern=SHA256)
    candidate_scene: str
    source_level_sha256_before: str = Field(pattern=SHA256)
    source_level_sha256_after: str = Field(pattern=SHA256)
    source_level_unchanged: bool
    protected_state_before: str = Field(pattern=SHA256)
    protected_state_after: str = Field(pattern=SHA256)
    generated_instance_count_before: int = Field(ge=0, le=10_000)
    generated_instance_count_after: int = Field(ge=0, le=10_000)
    intensity_before: float
    intensity_after: float
    temperature_before: float
    temperature_after: float
    candidate_level_sha256: str = Field(pattern=SHA256)
    corrected_beauty_path: str
    corrected_beauty_sha256: str = Field(pattern=SHA256)
    reconciled: bool
    completed_at: datetime


def compile_current_correction_work(state: AgentRunState) -> SceneCorrectionWorkDefinition:
    verdict = state.scene_candidate_visual_verdict
    parent = state.scene_candidate_work
    session = state.scene_sessions[-1] if state.scene_sessions else None
    if verdict is None or parent is None or session is None:
        raise ValueError("correction work requires a current visual verdict")
    evaluation = verdict.domain_evaluation
    if evaluation.status != "correction_required" or evaluation.failed_domains != ["lighting"]:
        raise ValueError("registered correction currently requires a lighting-only failure")
    if parent.status != "succeeded" or parent.outcome_sha256 is None:
        raise ValueError("correction work requires a succeeded parent candidate")
    intake = state.scene_candidate_intake
    if intake is None:
        raise ValueError("correction work requires the registered Unreal intake")

    preserved = {
        finding.domain: finding.evidence_sha256
        for finding in evaluation.findings
        if finding.status == "passed"
    }
    correction_payload = {
        "evaluation_sha256": evaluation.evaluation_sha256,
        "candidate_scene": evaluation.candidate_scene,
        "failed_domains": ["lighting"],
        "rerun_domains": ["lighting"],
        "preserved_evidence_sha256s": preserved,
        "lighting_intensity": 3.2,
        "lighting_temperature_kelvin": 7200.0,
    }
    correction_sha256 = canonical_sha256(correction_payload)
    correction_plan = SceneDomainCorrectionPlan(
        correction_id=f"domain-correction-{correction_sha256[:12]}",
        correction_sha256=correction_sha256,
        **correction_payload,
    )
    work_payload = {
        "run_id": state.run_id,
        "session_sha256": session.session_sha256,
        "parent_work_sha256": parent.definition.work_sha256,
        "parent_outcome_sha256": parent.outcome_sha256,
        "source_level_sha256": intake.evaluation_input.source_level_sha256,
        "candidate_plan_sha256": parent.definition.candidate_plan.plan_sha256,
        "candidate_scene": evaluation.candidate_scene,
        "evaluation_sha256": evaluation.evaluation_sha256,
        "correction_plan": correction_plan.model_dump(mode="json"),
    }
    work_sha256 = canonical_sha256(work_payload)
    return SceneCorrectionWorkDefinition(
        work_id=f"scene-correction-{work_sha256[:12]}",
        work_sha256=work_sha256,
        **work_payload,
    )


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def resolve_current_correction_beauty(
    project_root: Path, state: AgentRunState
) -> Path:
    receipt_path, receipt = resolve_current_correction_receipt(project_root, state)
    beauty = Path(receipt.corrected_beauty_path).resolve()
    try:
        beauty.relative_to(receipt_path.parent)
    except ValueError as exc:
        raise ValueError("corrected rerender escaped its registered work directory") from exc
    if not beauty.is_file() or file_sha256(beauty) != receipt.corrected_beauty_sha256:
        raise ValueError("corrected rerender content does not match its Unreal receipt")
    return beauty


def resolve_current_correction_receipt(
    project_root: Path, state: AgentRunState
) -> tuple[Path, UnrealLightingCorrectionReceipt]:
    work = state.scene_correction_work
    if work is None or work.status != "succeeded" or work.outcome_sha256 is None:
        raise ValueError("current lighting correction has no succeeded Unreal receipt")
    receipt_path = (
        project_root
        / "integrations"
        / "unreal"
        / "ArtFlowBridgeHost"
        / "Saved"
        / "ArtFlowSceneBridge"
        / "SceneCorrections"
        / work.definition.work_id
        / "lighting-correction-receipt.json"
    ).resolve()
    if not receipt_path.is_file() or file_sha256(receipt_path) != work.outcome_sha256:
        raise ValueError("registered lighting correction receipt does not match current work")
    receipt = UnrealLightingCorrectionReceipt.model_validate_json(
        receipt_path.read_text(encoding="utf-8-sig")
    )
    definition = work.definition
    if (
        receipt.work_id != definition.work_id
        or receipt.work_sha256 != definition.work_sha256
        or receipt.evaluation_sha256 != definition.evaluation_sha256
        or receipt.correction_sha256
        != definition.correction_plan.correction_sha256
        or receipt.source_level_sha256_before != definition.source_level_sha256
        or receipt.source_level_sha256_after != definition.source_level_sha256
        or not receipt.source_level_unchanged
        or receipt.protected_state_before != receipt.protected_state_after
        or receipt.generated_instance_count_before
        != receipt.generated_instance_count_after
    ):
        raise ValueError("lighting correction receipt widened or changed a preserved domain")
    return receipt_path, receipt


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
