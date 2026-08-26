from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from .contracts import ReceiptArtifact

ViolationKind = Literal[
    "protected_geometry_redesign",
    "sphere_relocation",
    "camera_framing_change",
    "ground_plane_composition_change",
]


class NegativeControlRequest(BaseModel):
    schema_id: Literal["negative-control-request/1"] = "negative-control-request/1"
    scene_package_id: str
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    beauty_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    intended_violations: list[ViolationKind] = Field(min_length=1)
    sent_input_kinds: list[Literal["beauty"]] = Field(default_factory=lambda: ["beauty"])
    withheld_input_kinds: list[Literal["depth", "world_normal", "object_id"]] = Field(
        default_factory=lambda: ["depth", "world_normal", "object_id"]
    )

    @model_validator(mode="after")
    def enforce_bounded_negative_control(self) -> NegativeControlRequest:
        if self.sent_input_kinds != ["beauty"]:
            raise ValueError("Negative control may send only the beauty pass")
        if set(self.withheld_input_kinds) != {"depth", "world_normal", "object_id"}:
            raise ValueError("Local tribunal passes must remain withheld")
        if len(self.intended_violations) != len(set(self.intended_violations)):
            raise ValueError("Negative-control violations must be unique")
        return self

    def fingerprint(self) -> str:
        return _sha256_json(self.model_dump(mode="json"))


class NegativeControlReceipt(BaseModel):
    schema_id: Literal["negative-control-receipt/1"] = "negative-control-receipt/1"
    control_id: str = Field(pattern=r"^negative-[a-f0-9]{20}$")
    purpose: Literal["attractive_invalid_control"] = "attractive_invalid_control"
    tool_id: Literal["codex-builtin-imagegen"] = "codex-builtin-imagegen"
    requested_model_family: Literal["gpt-image-2"] = "gpt-image-2"
    observed_model_id: None = None
    request_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact: ReceiptArtifact
    width: int = Field(ge=64, le=16384)
    height: int = Field(ge=64, le=16384)
    imported_at: AwareDatetime
    upstream_request_id: None = None

    @model_validator(mode="after")
    def require_content_addressed_png(self) -> NegativeControlReceipt:
        if self.artifact.media_type != "image/png":
            raise ValueError("Negative control must be a PNG")
        if self.artifact.sha256 not in self.artifact.path:
            raise ValueError("Negative-control path must contain its content hash")
        return self


class NegativeControlRecord(BaseModel):
    request: NegativeControlRequest
    receipt: NegativeControlReceipt

    @model_validator(mode="after")
    def bind_receipt(self) -> NegativeControlRecord:
        if self.receipt.request_binding_sha256 != self.request.fingerprint():
            raise ValueError("Negative-control receipt does not match request")
        return self


def _sha256_json(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
