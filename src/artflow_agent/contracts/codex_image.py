from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .execution import ReceiptArtifact


class CodexImageRequestBinding(BaseModel):
    """Exact, privacy-minimized request boundary for Codex built-in image generation."""

    schema_id: Literal["codex-image-request/1"] = "codex-image-request/1"
    scene_package_id: str = Field(min_length=1)
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    beauty_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    art_goal: str = Field(min_length=1)
    preserve: list[str] = Field(min_length=1)
    prohibit: list[str] = Field(min_length=1)
    sent_input_kinds: list[Literal["beauty"]] = Field(default_factory=lambda: ["beauty"])
    withheld_input_kinds: list[Literal["depth", "world_normal", "object_id"]] = Field(
        default_factory=lambda: ["depth", "world_normal", "object_id"]
    )
    output_count: Literal[1] = 1
    output_aspect_ratio: Literal["16:9"] = "16:9"
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def enforce_minimal_disclosure(self) -> CodexImageRequestBinding:
        if self.sent_input_kinds != ["beauty"]:
            raise ValueError("Codex image requests may send only the beauty pass")
        if set(self.withheld_input_kinds) != {"depth", "world_normal", "object_id"}:
            raise ValueError("All local-only tribunal passes must remain withheld")
        return self

    def fingerprint(self) -> str:
        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(canonical).hexdigest()


class CodexImageCandidateReceipt(BaseModel):
    """Normalized evidence for an image returned by the Codex built-in tool surface."""

    schema_id: Literal["codex-image-candidate-receipt/1"] = (
        "codex-image-candidate-receipt/1"
    )
    candidate_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,119}$")
    tool_id: Literal["codex-builtin-imagegen"] = "codex-builtin-imagegen"
    requested_model_family: Literal["gpt-image-2"] = "gpt-image-2"
    observed_model_id: None = None
    request_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact: ReceiptArtifact
    width: int = Field(ge=64, le=16384)
    height: int = Field(ge=64, le=16384)
    imported_at: AwareDatetime
    upstream_request_id: None = None
    adoption_status: Literal["unselected"] = "unselected"

    @model_validator(mode="after")
    def enforce_truthful_tool_receipt(self) -> CodexImageCandidateReceipt:
        if self.artifact.media_type != "image/png":
            raise ValueError("Codex image candidate must be a PNG")
        if self.artifact.sha256 not in self.artifact.path:
            raise ValueError("Codex image artifact path must be content-addressed")
        return self


class CodexImageCandidateRecord(BaseModel):
    request: CodexImageRequestBinding
    receipt: CodexImageCandidateReceipt

    @model_validator(mode="after")
    def bind_receipt_to_request(self) -> CodexImageCandidateRecord:
        if self.receipt.request_binding_sha256 != self.request.fingerprint():
            raise ValueError("Codex image receipt does not match its request binding")
        return self


def imported_at_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
