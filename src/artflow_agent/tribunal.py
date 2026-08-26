from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from PIL import Image, ImageFilter, ImageOps
from pydantic import AwareDatetime, BaseModel, Field, model_validator

CandidateRole = Literal["local_comfy", "codex_image", "negative_control"]


class TribunalArtifact(BaseModel):
    role: Literal["source", "local_comfy", "codex_image", "negative_control"]
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class EvaluationDossier(BaseModel):
    schema_id: Literal["evaluation-dossier/1"] = "evaluation-dossier/1"
    dossier_id: str = Field(pattern=r"^tribunal-[a-f0-9]{20}$")
    scene_package_id: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    beauty_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    preserve: list[str]
    prohibit: list[str]
    artifacts: list[TribunalArtifact] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def require_one_role_each(self) -> EvaluationDossier:
        if {item.role for item in self.artifacts} != {
            "source",
            "local_comfy",
            "codex_image",
        }:
            raise ValueError("Evaluation dossier requires source, local and Codex artifacts")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json", exclude={"dossier_id"})
        return _sha256_json(payload)


class EvaluatorClaim(BaseModel):
    claim_id: str
    evaluator_id: Literal["integrity_guard", "composition_guard"]
    candidate_role: CandidateRole
    claim: str
    method: str
    evidence_sha256: list[str] = Field(min_length=1)
    metric_name: str
    observed: float
    threshold: float
    comparator: Literal["eq", "lte", "gte"]
    verdict: Literal["pass", "fail"]
    hard_failure: bool
    limitation: str


class CandidateTribunalResult(BaseModel):
    candidate_role: CandidateRole
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    eligible: bool
    claims: list[EvaluatorClaim] = Field(min_length=3)

    @model_validator(mode="after")
    def hard_failures_control_eligibility(self) -> CandidateTribunalResult:
        expected = not any(
            claim.hard_failure and claim.verdict == "fail" for claim in self.claims
        )
        if self.eligible != expected:
            raise ValueError("Candidate eligibility must follow deterministic hard failures")
        return self


class TribunalReport(BaseModel):
    schema_id: Literal["tribunal-report/1"] = "tribunal-report/1"
    dossier: EvaluationDossier
    dossier_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluator_versions: dict[str, str]
    results: list[CandidateTribunalResult] = Field(min_length=2, max_length=2)
    adoption_status: Literal["unselected"] = "unselected"
    evaluated_at: AwareDatetime

    @model_validator(mode="after")
    def verify_dossier_and_results(self) -> TribunalReport:
        if self.dossier_sha256 != self.dossier.fingerprint():
            raise ValueError("Tribunal report dossier fingerprint does not match")
        if {item.candidate_role for item in self.results} != {
            "local_comfy",
            "codex_image",
        }:
            raise ValueError("Tribunal report requires both candidate results")
        artifacts = {item.role: item for item in self.dossier.artifacts}
        for result in self.results:
            expected = artifacts[result.candidate_role].artifact_sha256
            if result.artifact_sha256 != expected:
                raise ValueError("Tribunal result artifact does not match dossier")
            if any(
                claim.candidate_role != result.candidate_role
                or expected not in claim.evidence_sha256
                or claim.evaluator_id not in self.evaluator_versions
                for claim in result.claims
            ):
                raise ValueError("Tribunal claim evidence or evaluator identity is inconsistent")
        return self


def evaluate_dossier(
    dossier: EvaluationDossier,
    paths: dict[str, Path],
) -> TribunalReport:
    source = paths["source"]
    source_ratio = _aspect_ratio(source)
    results: list[CandidateTribunalResult] = []
    for evidence in dossier.artifacts:
        if evidence.role == "source":
            continue
        results.append(
            _evaluate_candidate(
                evidence,
                paths[evidence.role],
                source,
                dossier.beauty_sha256,
                source_ratio,
            )
        )
    return TribunalReport(
        dossier=dossier,
        dossier_sha256=dossier.fingerprint(),
        evaluator_versions={"integrity_guard": "1.0.0", "composition_guard": "1.0.0"},
        results=results,
        evaluated_at=datetime.now(UTC),
    )


def evaluate_negative_control(
    dossier: EvaluationDossier,
    evidence: TribunalArtifact,
    source_path: Path,
    control_path: Path,
) -> CandidateTribunalResult:
    if evidence.role != "negative_control":
        raise ValueError("Negative-control evaluation requires the negative_control role")
    return _evaluate_candidate(
        evidence,
        control_path,
        source_path,
        dossier.beauty_sha256,
        _aspect_ratio(source_path),
    )


def report_fingerprint(report: TribunalReport) -> str:
    return _sha256_json(report.model_dump(mode="json"))


def _evaluate_candidate(
    evidence: TribunalArtifact,
    candidate: Path,
    source: Path,
    beauty_sha256: str,
    source_ratio: float,
) -> CandidateTribunalResult:
    if evidence.role == "source":
        raise ValueError("Source evidence cannot be evaluated as a candidate")
    observed_hash = _sha256_file(candidate)
    integrity_pass = observed_hash == evidence.artifact_sha256
    ratio_drift = abs(_aspect_ratio(candidate) - source_ratio) / source_ratio
    layout_similarity = _edge_layout_similarity(source, candidate)
    claims = [
        _claim(
            evidence.role,
            "integrity_guard",
            "Persisted candidate bytes match the content-bound receipt.",
            "SHA-256 over persisted bytes compared with dossier artifact identity.",
            [evidence.artifact_sha256],
            "artifact_hash_match",
            1.0 if integrity_pass else 0.0,
            1.0,
            "eq",
            integrity_pass,
            True,
            "Authenticates bytes and binding only; it does not judge visual quality.",
        ),
        _claim(
            evidence.role,
            "composition_guard",
            "Landscape framing ratio remains within two percent of the Unreal source.",
            "Absolute normalized aspect-ratio drift after reading PNG headers.",
            [beauty_sha256, evidence.artifact_sha256],
            "aspect_ratio_drift",
            ratio_drift,
            0.02,
            "lte",
            ratio_drift <= 0.02,
            True,
            "Detects framing-ratio drift, not camera-pose or object-geometry changes.",
        ),
        _claim(
            evidence.role,
            "composition_guard",
            "Coarse edge-energy layout remains measurably related to the source.",
            "Cosine similarity of autocontrasted FIND_EDGES images normalized to 64x36.",
            [beauty_sha256, evidence.artifact_sha256],
            "coarse_edge_layout_similarity",
            layout_similarity,
            0.35,
            "gte",
            layout_similarity >= 0.35,
            False,
            "A low-resolution appearance proxy; it cannot prove semantic geometry preservation.",
        ),
    ]
    return CandidateTribunalResult(
        candidate_role=evidence.role,
        artifact_sha256=evidence.artifact_sha256,
        eligible=not any(c.hard_failure and c.verdict == "fail" for c in claims),
        claims=claims,
    )


def dossier_id_for(payload: dict[str, object]) -> str:
    return f"tribunal-{_sha256_json(payload)[:20]}"


def _claim(
    role: CandidateRole,
    evaluator: Literal["integrity_guard", "composition_guard"],
    claim: str,
    method: str,
    evidence: list[str],
    metric: str,
    observed: float,
    threshold: float,
    comparator: Literal["eq", "lte", "gte"],
    passed: bool,
    hard: bool,
    limitation: str,
) -> EvaluatorClaim:
    identity = _sha256_json({"role": role, "evaluator": evaluator, "metric": metric})[:16]
    return EvaluatorClaim(
        claim_id=f"claim-{identity}",
        evaluator_id=evaluator,
        candidate_role=role,
        claim=claim,
        method=method,
        evidence_sha256=evidence,
        metric_name=metric,
        observed=round(observed, 6),
        threshold=threshold,
        comparator=comparator,
        verdict="pass" if passed else "fail",
        hard_failure=hard,
        limitation=limitation,
    )


def _aspect_ratio(path: Path) -> float:
    with Image.open(path) as image:
        return image.width / image.height


def _edge_layout_similarity(source: Path, candidate: Path) -> float:
    def vector(path: Path) -> list[float]:
        with Image.open(path) as image:
            normalized = ImageOps.autocontrast(
                image.convert("L").resize((64, 36)).filter(ImageFilter.FIND_EDGES)
            )
            return [float(value) / 255.0 for value in normalized.tobytes()]

    left = vector(source)
    right = vector(candidate)
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return dot / norm if norm else 0.0


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
