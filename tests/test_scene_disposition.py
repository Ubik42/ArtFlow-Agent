from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.scene_disposition import (
    SceneCandidateAdoptionDecision,
    SessionCandidateExecutionReceipt,
    canonical_sha256,
    compile_adoption_decision,
    file_sha256,
)
from artflow_agent.scene_session import SceneCandidateDomainEvaluation, SceneCandidatePlan

ROOT = Path(__file__).resolve().parents[1]
M13 = ROOT / "artifacts/goal/m13-s2-sunlit-overgrown"
def inputs() -> tuple[
    SceneCandidateDomainEvaluation,
    SceneCandidatePlan,
    SessionCandidateExecutionReceipt,
]:
    return (
        SceneCandidateDomainEvaluation.model_validate_json(
            (M13 / "corrected-domain-evaluation.json").read_text(encoding="utf-8")
        ),
        SceneCandidatePlan.model_validate_json(
            (M13 / "corrected-candidate-plan.json").read_text(encoding="utf-8")
        ),
        SessionCandidateExecutionReceipt.model_validate_json(
            (M13 / "corrected-execution-receipt.json").read_text(encoding="utf-8")
        ),
    )


def content_files(
    tmp_path: Path, execution: SessionCandidateExecutionReceipt
) -> tuple[Path, Path, SessionCandidateExecutionReceipt]:
    candidate = tmp_path / "C_5e39f4fb72dc.umap"
    source = tmp_path / "ArtFlowDemo.umap"
    candidate.write_bytes(b"frozen-session-candidate")
    source.write_bytes(b"frozen-source-level")
    return (
        candidate,
        source,
        execution.model_copy(
            update={
                "candidate_level_sha256": file_sha256(candidate),
                "source_level_sha256_before": file_sha256(source),
                "source_level_sha256_after": file_sha256(source),
            }
        ),
    )


def compile_valid(tmp_path: Path) -> SceneCandidateAdoptionDecision:
    evaluation, plan, execution = inputs()
    candidate, source, execution = content_files(tmp_path, execution)
    return compile_adoption_decision(
        evaluation=evaluation,
        plan=plan,
        execution=execution,
        execution_receipt_sha256=file_sha256(M13 / "corrected-execution-receipt.json"),
        candidate_file=candidate,
        source_file=source,
    )


def test_accepted_session_candidate_compiles_content_addressed_publish(
    tmp_path: Path,
) -> None:
    decision = compile_valid(tmp_path)

    assert decision.orchestrator == "codex"
    assert decision.published_scene == (
        "/Game/ArtFlow/Published/AF_784907467248/"
        f"V_{decision.content_identity_sha256[:12]}"
    )


def test_correction_required_evaluation_cannot_be_adopted(tmp_path: Path) -> None:
    _, plan, execution = inputs()
    candidate, source, execution = content_files(tmp_path, execution)
    failed = SceneCandidateDomainEvaluation.model_validate_json(
        (M13 / "failure-domain-evaluation.json").read_text(encoding="utf-8")
    )

    with pytest.raises(ValueError, match="only an accepted domain evaluation"):
        compile_adoption_decision(
            evaluation=failed,
            plan=plan,
            execution=execution,
            execution_receipt_sha256=file_sha256(M13 / "corrected-execution-receipt.json"),
            candidate_file=candidate,
            source_file=source,
        )


def test_changed_candidate_bytes_cannot_be_adopted(tmp_path: Path) -> None:
    evaluation, plan, execution = inputs()
    candidate, source, execution = content_files(tmp_path, execution)
    changed = tmp_path / "candidate.umap"
    changed.write_bytes(candidate.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="candidate bytes changed"):
        compile_adoption_decision(
            evaluation=evaluation,
            plan=plan,
            execution=execution,
            execution_receipt_sha256=file_sha256(M13 / "corrected-execution-receipt.json"),
            candidate_file=changed,
            source_file=source,
        )


def test_changed_source_bytes_cannot_be_adopted(tmp_path: Path) -> None:
    evaluation, plan, execution = inputs()
    candidate, source, execution = content_files(tmp_path, execution)
    changed = tmp_path / "ArtFlowDemo.umap"
    changed.write_bytes(source.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="source level bytes changed"):
        compile_adoption_decision(
            evaluation=evaluation,
            plan=plan,
            execution=execution,
            execution_receipt_sha256=file_sha256(M13 / "corrected-execution-receipt.json"),
            candidate_file=candidate,
            source_file=changed,
        )


def test_publish_destination_cannot_escape_content_identity(tmp_path: Path) -> None:
    payload = compile_valid(tmp_path).model_dump(mode="json")
    payload["published_scene"] = "/Game/ArtFlow/Published/manual"
    unsigned = {
        key: value
        for key, value in payload.items()
        if key not in {"schema_id", "decision_id", "decision_sha256"}
    }
    digest = canonical_sha256(unsigned)
    payload["decision_id"] = f"scene-adoption-{digest[:16]}"
    payload["decision_sha256"] = digest

    with pytest.raises(ValidationError, match="content-addressed decision destination"):
        SceneCandidateAdoptionDecision.model_validate(payload)


def test_unknown_disposition_policy_is_rejected(tmp_path: Path) -> None:
    payload = json.loads(compile_valid(tmp_path).model_dump_json())
    payload["policy_version"] = "scene-disposition-policy/unknown"

    with pytest.raises(ValidationError, match="policy_version"):
        SceneCandidateAdoptionDecision.model_validate(payload)
