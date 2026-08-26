from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .multimodal_critic import MultimodalTribunalReport
from .tribunal import TribunalReport, report_fingerprint

ProductionCandidateRole = Literal["local_comfy", "codex_image"]


class AdoptionEvidence(BaseModel):
    base_tribunal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    multimodal_tribunal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    selected_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    deterministic_eligible: Literal[True] = True
    aesthetic_verdict: Literal["pass", "uncertain"]
    aesthetic_confidence: float = Field(ge=0, le=1)


class CandidateAdoptionDecision(BaseModel):
    schema_id: Literal["candidate-adoption-decision/1"] = (
        "candidate-adoption-decision/1"
    )
    decision_id: str = Field(pattern=r"^adoption-[a-f0-9]{20}$")
    selected_role: ProductionCandidateRole
    selected_candidate_id: str = Field(min_length=3, max_length=160)
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    status: Literal["adopted"] = "adopted"
    decided_by: Literal["codex-orchestrator"] = "codex-orchestrator"
    selection_policy: Literal["hard-eligible-then-visual-direction-v1"] = (
        "hard-eligible-then-visual-direction-v1"
    )
    evidence: AdoptionEvidence
    decision_basis: list[str] = Field(min_length=2, max_length=5)
    dissent_retained: list[str] = Field(default_factory=list, max_length=5)
    reasoning_capture: Literal["excluded"] = "excluded"

    @model_validator(mode="after")
    def require_exact_evidence_binding(self) -> CandidateAdoptionDecision:
        if self.artifact_sha256 != self.evidence.selected_artifact_sha256:
            raise ValueError("Adoption artifact must match the selected evidence")
        return self

    def fingerprint(self) -> str:
        return _sha256_json(self.model_dump(mode="json"))


def select_production_candidate(
    base: TribunalReport,
    multimodal: MultimodalTribunalReport,
    *,
    local_candidate_id: str,
    codex_candidate_id: str,
) -> CandidateAdoptionDecision:
    """Select one production candidate from persisted evidence without an interrupt."""
    base_sha = report_fingerprint(base)
    if multimodal.base_tribunal_sha256 != base_sha:
        raise ValueError("Multimodal evidence does not bind the supplied base tribunal")
    if base.adoption_status != "unselected" or (
        multimodal.production_adoption_status != "unselected"
    ):
        raise ValueError("Selection requires an unmodified pre-adoption tribunal")

    eligible = {
        result.candidate_role: result
        for result in base.results
        if result.candidate_role in {"local_comfy", "codex_image"} and result.eligible
    }
    if not eligible:
        raise ValueError("No production candidate passed deterministic eligibility")
    critic_by_role = {
        role: [claim for claim in multimodal.critic.claims if claim.candidate_role == role]
        for role in eligible
    }

    def score(role: ProductionCandidateRole) -> tuple[int, int, float]:
        claims = critic_by_role[role]
        aesthetic = next(
            (claim for claim in claims if claim.dimension == "aesthetic_coherence"),
            None,
        )
        if aesthetic is None:
            raise ValueError(f"Eligible candidate {role} has no aesthetic observation")
        return (
            1 if aesthetic.verdict == "pass" else 0,
            sum(claim.verdict == "pass" for claim in claims),
            aesthetic.confidence,
        )

    ranked = sorted(eligible, key=lambda role: (score(role), role), reverse=True)
    selected = ranked[0]
    if len(ranked) > 1 and score(ranked[0]) == score(ranked[1]):
        raise ValueError("Persisted evidence does not identify a unique candidate")
    result = eligible[selected]
    aesthetic = next(
        claim
        for claim in critic_by_role[selected]
        if claim.dimension == "aesthetic_coherence"
    )
    candidate_ids = {
        "local_comfy": local_candidate_id,
        "codex_image": codex_candidate_id,
    }
    dissent = []
    if selected == "codex_image" and "local_comfy" in eligible:
        local_layout = next(
            claim
            for claim in eligible["local_comfy"].claims
            if claim.metric_name == "coarse_edge_layout_similarity"
        )
        selected_layout = next(
            claim
            for claim in result.claims
            if claim.metric_name == "coarse_edge_layout_similarity"
        )
        dissent.append(
            "Local Comfy retains the stronger non-semantic edge-layout proxy "
            f"({local_layout.observed:.6f} vs {selected_layout.observed:.6f})."
        )

    multimodal_sha = multimodal.fingerprint()
    payload = {
        "base": base_sha,
        "multimodal": multimodal_sha,
        "role": selected,
        "artifact": result.artifact_sha256,
        "policy": "hard-eligible-then-visual-direction-v1",
    }
    return CandidateAdoptionDecision(
        decision_id=f"adoption-{_sha256_json(payload)[:20]}",
        selected_role=selected,
        selected_candidate_id=candidate_ids[selected],
        artifact_sha256=result.artifact_sha256,
        evidence=AdoptionEvidence(
            base_tribunal_sha256=base_sha,
            multimodal_tribunal_sha256=multimodal_sha,
            selected_artifact_sha256=result.artifact_sha256,
            aesthetic_verdict=aesthetic.verdict,
            aesthetic_confidence=aesthetic.confidence,
        ),
        decision_basis=[
            "The selected artifact passed every deterministic hard eligibility gate.",
            (
                "The bounded visual critic rated its aesthetic direction "
                f"{aesthetic.verdict} at {aesthetic.confidence:.2f} confidence."
            ),
            "The attractive-invalid control was excluded before ranking and cannot be adopted.",
        ],
        dissent_retained=dissent,
    )


def _sha256_json(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
