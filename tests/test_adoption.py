from __future__ import annotations

from pathlib import Path

import pytest

from artflow_agent.adoption import CandidateAdoptionDecision, select_production_candidate
from artflow_agent.multimodal_critic import MultimodalTribunalReport
from artflow_agent.tribunal import TribunalReport

ROOT = Path(__file__).parents[1]


def _reports() -> tuple[TribunalReport, MultimodalTribunalReport]:
    base = TribunalReport.model_validate_json(
        (ROOT / "artifacts/goal/m4-s1-tribunal/tribunal-report.json").read_text(
            encoding="utf-8"
        )
    )
    multimodal = MultimodalTribunalReport.model_validate_json(
        (
            ROOT
            / "artifacts/goal/m4-s2-negative-control/multimodal-tribunal-report.json"
        ).read_text(encoding="utf-8")
    )
    return base, multimodal


def test_orchestrator_selects_unique_eligible_visual_direction() -> None:
    base, multimodal = _reports()
    decision = select_production_candidate(
        base,
        multimodal,
        local_candidate_id="local-comfy:8029f4a558e3bfefbbfa",
        codex_candidate_id="codex-a8430dc9b8290bd658dd",
    )

    assert decision.selected_role == "codex_image"
    assert decision.artifact_sha256 == (
        "a8430dc9b8290bd658dd276cc7e9a9c490ca6a25a5accff70145a2d6704f54d5"
    )
    assert decision.decided_by == "codex-orchestrator"
    assert decision.reasoning_capture == "excluded"
    assert decision.dissent_retained


def test_hard_ineligible_candidate_cannot_enter_adoption_ranking() -> None:
    base, multimodal = _reports()
    decision = select_production_candidate(
        base,
        multimodal,
        local_candidate_id="local-comfy:8029f4a558e3bfefbbfa",
        codex_candidate_id="codex-a8430dc9b8290bd658dd",
    )
    payload = decision.model_dump(mode="json")
    payload["selected_role"] = "negative_control"

    with pytest.raises(ValueError, match="selected_role"):
        CandidateAdoptionDecision.model_validate(payload)
