from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract

DomainName = Literal["asset", "lighting", "material", "pcg"]


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class DomainFinding(StrictContract):
    evaluator_id: Literal["technical-judge-v1", "visual-critic-v1"]
    domain: DomainName
    verdict: Literal["pass", "fail"]
    hard_failure: bool
    metric: str = Field(min_length=1, max_length=120)
    observed: bool | int | float
    threshold: str = Field(min_length=1, max_length=120)
    evidence_sha256: list[str] = Field(min_length=1, max_length=8)


class SceneDeltaEvaluation(StrictContract):
    schema_id: Literal["scene-delta-evaluation/1"] = "scene-delta-evaluation/1"
    evaluation_id: str = Field(pattern=r"^m9-eval-[0-9a-f]{20}$")
    unreal_request_sha256: str = Field(pattern=SHA256_PATTERN)
    unreal_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    authored_render_sha256: str = Field(pattern=SHA256_PATTERN)
    validation_render_sha256: str = Field(pattern=SHA256_PATTERN)
    evaluator_versions: dict[str, str]
    findings: list[DomainFinding] = Field(min_length=8, max_length=16)
    failed_domains: list[DomainName]
    status: Literal["correction_required", "verified"]
    evaluated_at: datetime
    evaluation_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_evaluation(self) -> SceneDeltaEvaluation:
        expected = sorted({item.domain for item in self.findings if item.verdict == "fail"})
        if self.failed_domains != expected:
            raise ValueError("failed_domains must be derived from independent findings")
        if self.status != ("correction_required" if expected else "verified"):
            raise ValueError("evaluation status does not match failed domains")
        evaluators = {item.evaluator_id for item in self.findings}
        if evaluators != {"technical-judge-v1", "visual-critic-v1"}:
            raise ValueError("technical and visual evaluators must both report")
        unsigned = self.model_dump(mode="json", exclude={"evaluation_sha256"})
        if canonical_sha256(unsigned) != self.evaluation_sha256:
            raise ValueError("evaluation fingerprint mismatch")
        return self


class LightingCorrection(StrictContract):
    intensity: float = Field(ge=0, le=1000000)
    temperature_kelvin: float = Field(ge=1000, le=20000)


class DomainCorrectionPlan(StrictContract):
    schema_id: Literal["domain-correction-plan/1"] = "domain-correction-plan/1"
    correction_id: str = Field(pattern=r"^m9-correction-[0-9a-f]{20}$")
    evaluation_sha256: str = Field(pattern=SHA256_PATTERN)
    failed_domains: list[DomainName] = Field(min_length=1, max_length=4)
    rerun_domains: list[DomainName] = Field(min_length=1, max_length=4)
    preserved_domain_evidence: dict[DomainName, str]
    lighting: LightingCorrection | None = None
    idempotency_key: str = Field(pattern=r"^m9:correction:[0-9a-f]{32}$")
    plan_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_scope(self) -> DomainCorrectionPlan:
        if self.rerun_domains != self.failed_domains:
            raise ValueError("correction may rerun only failed domains")
        passed = {"asset", "lighting", "material", "pcg"} - set(self.failed_domains)
        if set(self.preserved_domain_evidence) != passed:
            raise ValueError("every successful domain must be fingerprint-locked")
        if ("lighting" in self.failed_domains) != (self.lighting is not None):
            raise ValueError("lighting values must exist exactly when lighting is corrected")
        unsigned = self.model_dump(mode="json", exclude={"plan_sha256"})
        if canonical_sha256(unsigned) != self.plan_sha256:
            raise ValueError("correction plan fingerprint mismatch")
        return self


class LightingPatchRequest(StrictContract):
    schema_id: Literal["lighting-domain-patch-request/1"] = "lighting-domain-patch-request/1"
    request_id: str = Field(pattern=r"^m9-light-[0-9a-f]{20}$")
    purpose: Literal["failure_fixture", "domain_correction"]
    candidate_scene_path: str = Field(pattern=r"^/Game/ArtFlow/Staging/[A-Za-z0-9_.-]+$")
    source_scene_sha256: str = Field(pattern=SHA256_PATTERN)
    protected_state_sha256: str = Field(pattern=SHA256_PATTERN)
    parent_unreal_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    correction_plan_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    intensity: float = Field(ge=0, le=1000000)
    temperature_kelvin: float = Field(ge=1000, le=20000)
    expected_instance_count: int = Field(ge=1, le=10000)
    expected_material_path: str = Field(pattern=r"^/Game/ArtFlow/[A-Za-z0-9_./-]+$")
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_request(self) -> LightingPatchRequest:
        if (self.purpose == "domain_correction") != (self.correction_plan_sha256 is not None):
            raise ValueError("only a correction request binds a correction plan")
        unsigned = self.model_dump(mode="json", exclude={"request_sha256"})
        if canonical_sha256(unsigned) != self.request_sha256:
            raise ValueError("lighting patch request fingerprint mismatch")
        return self


class LightingPatchReceipt(StrictContract):
    schema_id: Literal["lighting-domain-patch-receipt/1"] = "lighting-domain-patch-receipt/1"
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["executed", "reconciled"]
    candidate_scene_path: str
    intensity_before: float
    intensity_after: float
    temperature_before: float
    temperature_after: float
    generated_instance_count_before: int
    generated_instance_count_after: int
    material_path_before: str
    material_path_after: str
    source_scene_sha256_before: str = Field(pattern=SHA256_PATTERN)
    source_scene_sha256_after: str = Field(pattern=SHA256_PATTERN)
    protected_state_before: str = Field(pattern=SHA256_PATTERN)
    protected_state_after: str = Field(pattern=SHA256_PATTERN)
    completed_at: datetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_isolation(self) -> LightingPatchReceipt:
        if self.generated_instance_count_before != self.generated_instance_count_after:
            raise ValueError("lighting correction changed the PCG domain")
        if self.material_path_before != self.material_path_after:
            raise ValueError("lighting correction changed the material domain")
        if self.source_scene_sha256_before != self.source_scene_sha256_after:
            raise ValueError("lighting correction changed the source scene")
        if self.protected_state_before != self.protected_state_after:
            raise ValueError("lighting correction changed a protected actor")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("lighting patch receipt fingerprint mismatch")
        return self


class VerifiedDispositionReceipt(StrictContract):
    schema_id: Literal["verified-scene-disposition-receipt/1"] = "verified-scene-disposition-receipt/1"
    disposition_id: str = Field(pattern=r"^m9-disposition-[0-9a-f]{20}$")
    disposition: Literal["published", "discarded"]
    evaluation_sha256: str = Field(pattern=SHA256_PATTERN)
    correction_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_scene_path: str
    published_scene_path: str | None = None
    published_scene_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    source_scene_sha256_before: str = Field(pattern=SHA256_PATTERN)
    source_scene_sha256_after: str = Field(pattern=SHA256_PATTERN)
    duplicate_side_effect_count: Literal[0] = 0
    completed_at: datetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_disposition(self) -> VerifiedDispositionReceipt:
        if self.source_scene_sha256_before != self.source_scene_sha256_after:
            raise ValueError("disposition changed the source scene")
        published = self.published_scene_path is not None and self.published_scene_sha256 is not None
        if published != (self.disposition == "published"):
            raise ValueError("published disposition requires a content-bound published scene")
        unsigned = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if canonical_sha256(unsigned) != self.receipt_sha256:
            raise ValueError("disposition receipt fingerprint mismatch")
        return self


class VerifiedDispositionRequest(StrictContract):
    schema_id: Literal["verified-scene-disposition-request/1"] = "verified-scene-disposition-request/1"
    disposition_id: str = Field(pattern=r"^m9-disposition-[0-9a-f]{20}$")
    disposition: Literal["published", "discarded"]
    evaluation_sha256: str = Field(pattern=SHA256_PATTERN)
    correction_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    candidate_scene_path: str = Field(pattern=r"^/Game/ArtFlow/Staging/[A-Za-z0-9_.-]+$")
    candidate_scene_sha256: str = Field(pattern=SHA256_PATTERN)
    published_scene_path: str | None = Field(
        default=None, pattern=r"^/Game/ArtFlow/Published/[A-Za-z0-9_.-]+$"
    )
    source_scene_sha256: str = Field(pattern=SHA256_PATTERN)
    idempotency_key: str = Field(pattern=r"^m9:disposition:[0-9a-f]{32}$")
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_request(self) -> VerifiedDispositionRequest:
        if (self.published_scene_path is not None) != (self.disposition == "published"):
            raise ValueError("only published disposition has a published scene path")
        unsigned = self.model_dump(mode="json", exclude={"request_sha256"})
        if canonical_sha256(unsigned) != self.request_sha256:
            raise ValueError("disposition request fingerprint mismatch")
        return self


LifecycleEventType = Literal[
    "run_created",
    "evaluation_recorded",
    "correction_reserved",
    "correction_submitted",
    "correction_receipt_recorded",
    "verification_recorded",
    "disposition_reserved",
    "disposition_submitted",
    "disposition_receipt_recorded",
]


class LifecycleEvent(StrictContract):
    sequence: int
    event_type: LifecycleEventType
    idempotency_key: str
    payload: dict[str, object]
    payload_sha256: str = Field(pattern=SHA256_PATTERN)
    occurred_at: datetime


class SceneLifecycleLedger:
    """Small append-only control plane for one staged 3D candidate lifecycle."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS scene_lifecycle_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                occurred_at TEXT NOT NULL)"""
            )

    def append(
        self, event_type: LifecycleEventType, idempotency_key: str, payload: dict[str, object]
    ) -> LifecycleEvent:
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_sha = hashlib.sha256(payload_json.encode()).hexdigest()
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                "SELECT sequence,event_type,payload_json,payload_sha256,occurred_at FROM scene_lifecycle_events WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if row:
                if row[1] != event_type or row[2] != payload_json:
                    raise ValueError("idempotency key was reused with different lifecycle evidence")
                return self._event(row, idempotency_key)
            self._assert_transition(connection, event_type)
            cursor = connection.execute(
                "INSERT INTO scene_lifecycle_events(event_type,idempotency_key,payload_json,payload_sha256,occurred_at) VALUES(?,?,?,?,?)",
                (event_type, idempotency_key, payload_json, payload_sha, now),
            )
            row = (cursor.lastrowid, event_type, payload_json, payload_sha, now)
        return self._event(row, idempotency_key)

    def events(self) -> list[LifecycleEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT sequence,event_type,payload_json,payload_sha256,occurred_at,idempotency_key FROM scene_lifecycle_events ORDER BY sequence"
            ).fetchall()
        return [
            LifecycleEvent(
                sequence=row[0], event_type=row[1], payload=json.loads(row[2]),
                payload_sha256=row[3], occurred_at=row[4], idempotency_key=row[5]
            )
            for row in rows
        ]

    def _assert_transition(self, connection: sqlite3.Connection, event_type: str) -> None:
        prior = [row[0] for row in connection.execute(
            "SELECT event_type FROM scene_lifecycle_events ORDER BY sequence"
        )]
        allowed = {
            "run_created": [],
            "evaluation_recorded": ["run_created"],
            "correction_reserved": ["evaluation_recorded"],
            "correction_submitted": ["correction_reserved"],
            "correction_receipt_recorded": ["correction_submitted"],
            "verification_recorded": ["correction_receipt_recorded"],
            "disposition_reserved": ["verification_recorded"],
            "disposition_submitted": ["disposition_reserved"],
            "disposition_receipt_recorded": ["disposition_submitted"],
        }
        required = allowed[event_type]
        if not prior and event_type != "run_created":
            raise ValueError("lifecycle must start with run_created")
        if prior and event_type == "run_created":
            raise ValueError("lifecycle can contain only one run_created event")
        if required and prior[-1] not in required:
            raise ValueError(f"illegal lifecycle transition {prior[-1]} -> {event_type}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    @staticmethod
    def _event(row: tuple[object, ...], key: str) -> LifecycleEvent:
        return LifecycleEvent(
            sequence=int(row[0]), event_type=str(row[1]), idempotency_key=key,
            payload=json.loads(str(row[2])), payload_sha256=str(row[3]), occurred_at=str(row[4])
        )
