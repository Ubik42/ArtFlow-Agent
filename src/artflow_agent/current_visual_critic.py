from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .scene_session import (
    DOMAIN_ORDER,
    SceneCandidateDomainEvaluation,
    SceneDomain,
    SceneDomainFinding,
)

if TYPE_CHECKING:
    from .agent_runtime import AgentRunState


SHA256 = r"^[a-f0-9]{64}$"
VisualDimension = Literal[
    "camera_composition",
    "protected_structure",
    "spatial_readability",
    "lighting_direction",
    "visual_coherence",
]
VISUAL_DIMENSIONS: tuple[VisualDimension, ...] = (
    "camera_composition",
    "protected_structure",
    "spatial_readability",
    "lighting_direction",
    "visual_coherence",
)
CURRENT_VISUAL_RUBRIC = {
    "schema_id": "artflow-current-visual-rubric/1",
    "dimensions": list(VISUAL_DIMENSIONS),
    "precedence": "deterministic_failures_cannot_be_overridden",
    "uncertain_policy": "treat_as_failed_for_domain_verdict",
}
CURRENT_VISUAL_RUBRIC_SHA256 = hashlib.sha256(
    json.dumps(
        CURRENT_VISUAL_RUBRIC,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()


class CurrentVisualClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: VisualDimension
    verdict: Literal["passed", "failed", "uncertain"]
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=8, max_length=300)


class CurrentCandidateVisualObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-current-candidate-visual-observation/1"] = (
        "artflow-current-candidate-visual-observation/1"
    )
    observation_id: str
    observation_sha256: str = Field(pattern=SHA256)
    evaluator_id: Literal["codex-native-multimodal-critic"] = (
        "codex-native-multimodal-critic"
    )
    evaluator_surface: Literal["codex-app-current-images"] = "codex-app-current-images"
    input_sha256: str = Field(pattern=SHA256)
    source_beauty_sha256: str = Field(pattern=SHA256)
    candidate_beauty_sha256: str = Field(pattern=SHA256)
    rubric_sha256: Literal[CURRENT_VISUAL_RUBRIC_SHA256] = CURRENT_VISUAL_RUBRIC_SHA256
    claims: list[CurrentVisualClaim] = Field(min_length=5, max_length=5)
    recommended_failed_domains: list[SceneDomain]

    @model_validator(mode="after")
    def verify_observation(self) -> CurrentCandidateVisualObservation:
        if [claim.dimension for claim in self.claims] != list(VISUAL_DIMENSIONS):
            raise ValueError("current visual claims must follow the registered rubric order")
        if len(set(self.recommended_failed_domains)) != len(
            self.recommended_failed_domains
        ):
            raise ValueError("current visual failed domains must be unique")
        ordered = [
            domain
            for domain in DOMAIN_ORDER
            if domain in self.recommended_failed_domains
        ]
        if self.recommended_failed_domains != ordered:
            raise ValueError("current visual failed domains must follow domain order")
        payload = self.model_dump(
            mode="json", exclude={"schema_id", "observation_id", "observation_sha256"}
        )
        expected = canonical_sha256(payload)
        if self.observation_sha256 != expected:
            raise ValueError("current visual observation hash is invalid")
        if self.observation_id != f"current-visual-observation-{expected[:12]}":
            raise ValueError("current visual observation id is invalid")
        return self


class CurrentCandidateDomainVerdictRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technical_intake_sha256: str = Field(pattern=SHA256)
    visual_observation: CurrentCandidateVisualObservation
    domain_evaluation: SceneCandidateDomainEvaluation

    @model_validator(mode="after")
    def verify_chain(self) -> CurrentCandidateDomainVerdictRecord:
        if self.visual_observation.input_sha256 != self.technical_intake_sha256:
            raise ValueError("visual observation references another technical intake")
        return self


def seal_visual_observation(payload: dict[str, object]) -> CurrentCandidateVisualObservation:
    canonical_payload = {
        "evaluator_id": "codex-native-multimodal-critic",
        "evaluator_surface": "codex-app-current-images",
        "rubric_sha256": CURRENT_VISUAL_RUBRIC_SHA256,
        **payload,
    }
    digest = canonical_sha256(canonical_payload)
    return CurrentCandidateVisualObservation(
        observation_id=f"current-visual-observation-{digest[:12]}",
        observation_sha256=digest,
        **canonical_payload,
    )


def compile_current_domain_verdict(
    state: AgentRunState,
    observation: CurrentCandidateVisualObservation,
) -> CurrentCandidateDomainVerdictRecord:
    intake = state.scene_candidate_intake
    work = state.scene_candidate_work
    if intake is None or work is None:
        raise ValueError("current visual verdict requires persisted technical intake")
    technical = intake.technical_evaluation
    evaluation_input = intake.evaluation_input
    if technical.status != "eligible_for_visual_review" or technical.failed_domains:
        raise ValueError("a rejected technical intake cannot enter visual scoring")
    if (
        observation.input_sha256 != evaluation_input.input_sha256
        or observation.source_beauty_sha256 != evaluation_input.source_beauty_sha256
        or observation.candidate_beauty_sha256
        != evaluation_input.candidate_beauty_sha256
    ):
        raise ValueError("visual observation references another current candidate")

    claim_by_dimension = {claim.dimension: claim for claim in observation.claims}
    selected_domains = [node.domain for node in state.scene_sessions[-1].draft.nodes]
    domains = [
        domain
        for domain in DOMAIN_ORDER
        if domain == "image" or domain in selected_domains
    ]
    findings: list[SceneDomainFinding] = []
    for domain in domains:
        relevant_dimensions = {
            "image": ("camera_composition", "protected_structure"),
            "material": ("visual_coherence",),
            "asset": ("protected_structure", "visual_coherence"),
            "pcg": ("protected_structure", "spatial_readability"),
            "lighting": ("lighting_direction", "visual_coherence"),
        }[domain]
        claims = [claim_by_dimension[item] for item in relevant_dimensions]
        visual_pass = all(claim.verdict == "passed" for claim in claims)
        recommended_fail = domain in observation.recommended_failed_domains
        passed = visual_pass and not recommended_fail
        reason = "；".join(claim.rationale for claim in claims)
        evidence = {
            "technical_evaluation_sha256": technical.evaluation_sha256,
            "visual_observation_sha256": observation.observation_sha256,
            "domain": domain,
            "claims": [claim.model_dump(mode="json") for claim in claims],
            "hard_gate_precedence": True,
        }
        findings.append(
            SceneDomainFinding(
                domain=domain,
                status="passed" if passed else "failed",
                reason=reason,
                evidence_sha256=canonical_sha256(evidence),
            )
        )

    failed_domains = [finding.domain for finding in findings if finding.status == "failed"]
    evaluation_payload = {
        "plan_sha256": work.definition.candidate_plan.plan_sha256,
        "candidate_scene": evaluation_input.candidate_scene,
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "failed_domains": failed_domains,
        "status": "correction_required" if failed_domains else "accepted",
    }
    evaluation_sha256 = canonical_sha256(evaluation_payload)
    evaluation = SceneCandidateDomainEvaluation(
        evaluation_id=f"domain-evaluation-{evaluation_sha256[:12]}",
        evaluation_sha256=evaluation_sha256,
        **evaluation_payload,
    )
    return CurrentCandidateDomainVerdictRecord(
        technical_intake_sha256=evaluation_input.input_sha256,
        visual_observation=observation,
        domain_evaluation=evaluation,
    )


def canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
