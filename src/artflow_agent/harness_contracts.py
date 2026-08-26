from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field

HarnessDomain = Literal["context", "capability", "routing", "policy", "recovery", "memory"]


class HarnessCitation(BaseModel):
    citation_type: Literal["event_hash", "scorecard_sha256", "contract"]
    value: str
    label: str


class HarnessCaseResult(BaseModel):
    case_id: str
    domain: HarnessDomain
    passed: bool
    expected: str
    observed: str
    latency_ms: float = Field(ge=0)
    fixture_cost_usd: float = Field(default=0, ge=0)
    citations: list[HarnessCitation] = Field(min_length=1)


class HarnessMetric(BaseModel):
    metric_id: str
    value: float
    unit: Literal["ratio", "count", "milliseconds", "usd"]
    numerator: float
    denominator: float = Field(gt=0)
    provenance: str


class HarnessScorecard(BaseModel):
    schema_id: Literal["artflow-harness-scorecard/1"] = "artflow-harness-scorecard/1"
    suite_version: Literal["m5-s3-harness-suite/1"] = "m5-s3-harness-suite/1"
    run_id: str
    passed_cases: int = Field(ge=0)
    total_cases: int = Field(ge=1)
    cases: list[HarnessCaseResult]
    metrics: list[HarnessMetric]
    source_scorecards: dict[str, str]
    limitations: list[str]
    scorecard_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    def expected_sha256(self) -> str:
        payload = self.model_dump(mode="json", exclude={"scorecard_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
