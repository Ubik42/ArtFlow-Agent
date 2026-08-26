from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MemoryKind = Literal["episodic", "semantic", "procedural"]
MemoryStatus = Literal["proposed", "active", "rejected", "superseded"]
MemoryScope = Literal["project", "shared"]


class MemoryProposal(BaseModel):
    schema_id: Literal["artflow-memory-proposal/1"] = "artflow-memory-proposal/1"
    memory_id: str = Field(pattern=r"^memory-[a-z0-9-]{8,80}$")
    kind: MemoryKind
    project_id: str = Field(min_length=3, max_length=160)
    subject_key: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,119}$")
    value: str = Field(min_length=1, max_length=800)
    tags: list[str] = Field(min_length=1, max_length=12)
    version: int = Field(ge=1)
    source_run_id: str
    source_event_hashes: list[str] = Field(min_length=1, max_length=16)
    source_scope: Literal["project_private"] = "project_private"
    target_scope: MemoryScope = "project"
    supersedes_memory_id: str | None = None
    content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_identity(self) -> MemoryProposal:
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("Memory tags must be unique")
        if len(set(self.source_event_hashes)) != len(self.source_event_hashes):
            raise ValueError("Memory source event hashes must be unique")
        if self.content_sha256 != self.expected_content_sha256():
            raise ValueError("Memory content hash does not match its governed payload")
        return self

    def expected_content_sha256(self) -> str:
        payload = {
            "kind": self.kind,
            "project_id": self.project_id,
            "subject_key": self.subject_key,
            "value": self.value,
            "tags": sorted(self.tags),
            "version": self.version,
            "source_run_id": self.source_run_id,
            "source_event_hashes": sorted(self.source_event_hashes),
            "source_scope": self.source_scope,
            "target_scope": self.target_scope,
            "supersedes_memory_id": self.supersedes_memory_id,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class MemoryPolicyDecision(BaseModel):
    schema_id: Literal["artflow-memory-policy-decision/1"] = (
        "artflow-memory-policy-decision/1"
    )
    decision_id: str = Field(pattern=r"^memory-policy-[a-f0-9]{16}$")
    proposal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    verdict: Literal["activate", "reject"]
    reason_codes: list[str] = Field(min_length=1)
    superseded_memory_id: str | None = None
    policy_id: Literal["project-memory-policy/1"] = "project-memory-policy/1"


class MemoryRecord(BaseModel):
    proposal: MemoryProposal
    status: MemoryStatus
    policy_decision: MemoryPolicyDecision | None = None
    superseded_by_memory_id: str | None = None


class MemoryQuery(BaseModel):
    project_id: str
    kinds: list[MemoryKind] = Field(default_factory=list, max_length=3)
    subject_keys: list[str] = Field(default_factory=list, max_length=12)
    tags: list[str] = Field(default_factory=list, max_length=12)
    limit: int = Field(default=5, ge=1, le=20)


class MemoryCitation(BaseModel):
    memory_id: str
    kind: MemoryKind
    subject_key: str
    value: str
    version: int
    content_sha256: str
    source_event_hashes: list[str]


class MemoryRetrievalResult(BaseModel):
    schema_id: Literal["artflow-memory-retrieval/1"] = "artflow-memory-retrieval/1"
    query: MemoryQuery
    citations: list[MemoryCitation]
    retrieval_mode: Literal["exact_metadata"] = "exact_metadata"
    truncated: bool


class MemoryEvalCase(BaseModel):
    case_id: str
    passed: bool
    expected: str
    observed: str
    latency_ms: float = Field(ge=0)
    evidence_memory_ids: list[str] = Field(default_factory=list)


class MemoryScorecard(BaseModel):
    schema_id: Literal["artflow-memory-scorecard/1"] = "artflow-memory-scorecard/1"
    suite_version: Literal["m5-s2-memory-suite/1"] = "m5-s2-memory-suite/1"
    passed_cases: int = Field(ge=0)
    total_cases: int = Field(ge=1)
    retrieval_precision: float = Field(ge=0, le=1)
    conflict_rejection_rate: float = Field(ge=0, le=1)
    total_latency_ms: float = Field(ge=0)
    cases: list[MemoryEvalCase]
    limitations: list[str]

    def fingerprint(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode("utf-8")).hexdigest()


def build_memory_proposal(
    *,
    memory_id: str,
    kind: MemoryKind,
    project_id: str,
    subject_key: str,
    value: str,
    tags: list[str],
    version: int,
    source_run_id: str,
    source_event_hashes: list[str],
    target_scope: MemoryScope = "project",
    supersedes_memory_id: str | None = None,
) -> MemoryProposal:
    data = {
        "memory_id": memory_id,
        "kind": kind,
        "project_id": project_id,
        "subject_key": subject_key,
        "value": value,
        "tags": tags,
        "version": version,
        "source_run_id": source_run_id,
        "source_event_hashes": source_event_hashes,
        "target_scope": target_scope,
        "supersedes_memory_id": supersedes_memory_id,
    }
    unchecked = MemoryProposal.model_construct(
        **data,
        source_scope="project_private",
        content_sha256="0" * 64,
    )
    return MemoryProposal.model_validate(
        {**data, "content_sha256": unchecked.expected_content_sha256()}
    )


def decide_memory_policy(
    proposal: MemoryProposal,
    records: list[MemoryRecord],
) -> MemoryPolicyDecision:
    active = [
        record
        for record in records
        if record.status == "active"
        and record.proposal.project_id == proposal.project_id
        and record.proposal.kind == proposal.kind
        and record.proposal.subject_key == proposal.subject_key
    ]
    verdict: Literal["activate", "reject"] = "activate"
    reason_codes = ["project_scope_and_sources_verified"]
    superseded: str | None = None
    if proposal.target_scope == "shared":
        verdict = "reject"
        reason_codes = ["shared_scope_authority_missing"]
    elif active:
        current = max(active, key=lambda item: item.proposal.version)
        if proposal.version <= current.proposal.version:
            verdict = "reject"
            reason_codes = ["stale_version"]
        elif proposal.supersedes_memory_id != current.proposal.memory_id:
            verdict = "reject"
            reason_codes = ["conflict_requires_explicit_supersession"]
        elif proposal.version != current.proposal.version + 1:
            verdict = "reject"
            reason_codes = ["non_contiguous_version"]
        else:
            reason_codes = ["verified_contiguous_supersession"]
            superseded = current.proposal.memory_id
    elif proposal.version != 1 or proposal.supersedes_memory_id is not None:
        verdict = "reject"
        reason_codes = ["invalid_initial_version"]
    proposal_hash = proposal.content_sha256
    identity = hashlib.sha256(
        f"{proposal_hash}:{verdict}:{','.join(reason_codes)}:{superseded or ''}".encode()
    ).hexdigest()[:16]
    return MemoryPolicyDecision(
        decision_id=f"memory-policy-{identity}",
        proposal_sha256=proposal_hash,
        verdict=verdict,
        reason_codes=reason_codes,
        superseded_memory_id=superseded,
    )


def retrieve_memory(
    records: list[MemoryRecord], query: MemoryQuery
) -> MemoryRetrievalResult:
    matches = [
        record
        for record in records
        if record.status == "active"
        and record.proposal.project_id == query.project_id
        and (not query.kinds or record.proposal.kind in query.kinds)
        and (not query.subject_keys or record.proposal.subject_key in query.subject_keys)
        and (not query.tags or set(query.tags).issubset(record.proposal.tags))
    ]
    matches.sort(
        key=lambda item: (
            item.proposal.kind,
            item.proposal.subject_key,
            -item.proposal.version,
        )
    )
    citations = [
        MemoryCitation(
            memory_id=record.proposal.memory_id,
            kind=record.proposal.kind,
            subject_key=record.proposal.subject_key,
            value=record.proposal.value,
            version=record.proposal.version,
            content_sha256=record.proposal.content_sha256,
            source_event_hashes=record.proposal.source_event_hashes,
        )
        for record in matches[: query.limit]
    ]
    return MemoryRetrievalResult(
        query=query,
        citations=citations,
        truncated=len(matches) > query.limit,
    )
