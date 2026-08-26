from __future__ import annotations

import hashlib

from pydantic import AwareDatetime, BaseModel, Field


class RecoveryCaseResult(BaseModel):
    case_id: str
    passed: bool
    recovery_outcome: str
    provider_side_effect_count: int = Field(ge=0)
    adoption_side_effect_count: int = Field(default=0, ge=0)
    revision_side_effect_count: int = Field(default=0, ge=0)
    terminal_event_count: int = Field(ge=0)
    duplicate_side_effect_count: int = Field(ge=0)
    recovery_latency_ms: float = Field(ge=0)
    trace_path: str | None = None
    event_database_path: str
    final_event_sequence: int = Field(ge=1)
    evidence_event_hashes: list[str]
    limitation: str | None = None


class RecoveryScorecard(BaseModel):
    schema_id: str = "artflow-recovery-scorecard/1"
    matrix_version: str
    generated_at: AwareDatetime
    passed_cases: int = Field(ge=0)
    total_cases: int = Field(ge=1)
    duplicate_side_effect_count: int = Field(ge=0)
    recovery_latency_ms_total: float = Field(ge=0)
    cases: list[RecoveryCaseResult]
    limitations: list[str]

    def fingerprint(self) -> str:
        payload = self.model_dump_json(exclude={"generated_at"})
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
