from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .negative_control import NegativeControlRecord
from .tribunal import CandidateRole, CandidateTribunalResult

CriticDimension = Literal[
    "aesthetic_coherence",
    "source_constraint_compliance",
    "protected_geometry_preservation",
    "camera_composition_preservation",
]


class CriticRubric(BaseModel):
    schema_id: Literal["visual-critic-rubric/1"] = "visual-critic-rubric/1"
    rubric_id: Literal["artflow-scene-direction-v1"] = "artflow-scene-direction-v1"
    dimensions: list[CriticDimension] = Field(min_length=4, max_length=4)
    instruction: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def require_all_dimensions(self) -> CriticRubric:
        expected = {
            "aesthetic_coherence",
            "source_constraint_compliance",
            "protected_geometry_preservation",
            "camera_composition_preservation",
        }
        if set(self.dimensions) != expected:
            raise ValueError("Visual critic rubric dimensions are incomplete")
        return self

    def fingerprint(self) -> str:
        return _sha256_json(self.model_dump(mode="json"))


class CriticInput(BaseModel):
    role: Literal["source", "local_comfy", "codex_image", "negative_control"]
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class CriticClaim(BaseModel):
    claim_id: str = Field(pattern=r"^critic-[a-f0-9]{16}$")
    candidate_role: CandidateRole
    dimension: CriticDimension
    verdict: Literal["pass", "fail", "uncertain"]
    confidence: float = Field(ge=0, le=1)
    observation: str = Field(min_length=1, max_length=500)
    limitation: str = Field(min_length=1, max_length=500)
    evidence_sha256: list[str] = Field(min_length=2, max_length=2)


class MultimodalCriticObservation(BaseModel):
    schema_id: Literal["multimodal-critic-observation/1"] = (
        "multimodal-critic-observation/1"
    )
    critic_id: Literal["codex-visual-critic"] = "codex-visual-critic"
    critic_surface: Literal["codex-native-multimodal"] = "codex-native-multimodal"
    observed_model_id: None = None
    rubric: CriticRubric
    rubric_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    inputs: list[CriticInput] = Field(min_length=4, max_length=4)
    claims: list[CriticClaim] = Field(min_length=6)
    observed_at: AwareDatetime
    reasoning_capture: Literal["excluded"] = "excluded"

    @model_validator(mode="after")
    def verify_bounded_observation(self) -> MultimodalCriticObservation:
        if self.rubric_sha256 != self.rubric.fingerprint():
            raise ValueError("Critic rubric hash does not match")
        roles = {item.role for item in self.inputs}
        if roles != {"source", "local_comfy", "codex_image", "negative_control"}:
            raise ValueError("Critic inputs must contain the bounded four-image set")
        source_hash = next(item.artifact_sha256 for item in self.inputs if item.role == "source")
        by_role = {item.role: item.artifact_sha256 for item in self.inputs}
        if any(
            claim.evidence_sha256 != [source_hash, by_role[claim.candidate_role]]
            for claim in self.claims
        ):
            raise ValueError("Critic claims must cite source then candidate hashes")
        if any(
            not any(claim.candidate_role == role for claim in self.claims)
            for role in ("local_comfy", "codex_image", "negative_control")
        ):
            raise ValueError("Critic must assess every candidate role")
        return self

    def fingerprint(self) -> str:
        return _sha256_json(self.model_dump(mode="json"))


class EvaluatorDisagreement(BaseModel):
    candidate_role: CandidateRole
    subject: str
    deterministic_verdict: Literal["pass", "fail"]
    critic_verdict: Literal["pass", "fail", "uncertain"]
    resolution: Literal["hard_gate_precedence", "visible_no_override"]


class MultimodalTribunalReport(BaseModel):
    schema_id: Literal["multimodal-tribunal-report/1"] = "multimodal-tribunal-report/1"
    report_id: str = Field(pattern=r"^multimodal-[a-f0-9]{20}$")
    base_tribunal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    negative_control: NegativeControlRecord
    deterministic_negative_result: CandidateTribunalResult
    critic: MultimodalCriticObservation
    disagreements: list[EvaluatorDisagreement] = Field(min_length=1)
    negative_control_status: Literal["rejected"] = "rejected"
    production_adoption_status: Literal["unselected"] = "unselected"

    @model_validator(mode="after")
    def enforce_hard_failure_precedence(self) -> MultimodalTribunalReport:
        result = self.deterministic_negative_result
        if result.candidate_role != "negative_control":
            raise ValueError("Extended tribunal must evaluate the negative-control role")
        if result.artifact_sha256 != self.negative_control.receipt.artifact.sha256:
            raise ValueError("Negative-control result does not match its receipt")
        if result.eligible or not any(
            claim.hard_failure and claim.verdict == "fail" for claim in result.claims
        ):
            raise ValueError("Negative control must be rejected by a deterministic hard gate")
        aesthetic = [
            claim
            for claim in self.critic.claims
            if claim.candidate_role == "negative_control"
            and claim.dimension == "aesthetic_coherence"
        ]
        if len(aesthetic) != 1 or aesthetic[0].verdict != "pass":
            raise ValueError("Negative control must establish the attractive-invalid conflict")
        if any(item.resolution != "hard_gate_precedence" for item in self.disagreements):
            raise ValueError("Evaluator disagreement must preserve hard-gate precedence")
        return self

    def fingerprint(self) -> str:
        return _sha256_json(self.model_dump(mode="json"))


def critic_claim_id(role: CandidateRole, dimension: CriticDimension) -> str:
    return f"critic-{_sha256_json({'role': role, 'dimension': dimension})[:16]}"


def multimodal_report_id(payload: object) -> str:
    return f"multimodal-{_sha256_json(payload)[:20]}"


def _sha256_json(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
