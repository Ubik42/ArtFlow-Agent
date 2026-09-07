from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class SceneConditioningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["artflow-scene-conditioning-request/1"] = (
        "artflow-scene-conditioning-request/1"
    )
    request_id: str = Field(pattern=r"^scene-condition-[a-f0-9]{16}$")
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scene_package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference_beauty_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    conditioning_pass: Literal["depth", "world_normal"]
    conditioning_pass_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    conditioning_input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    capability_id: Literal["comfy.scene_depth_reference.flux2_klein.v1"]
    recipe_id: Literal["composition-preserving-v1"]
    prompt: str = Field(min_length=20, max_length=1000)
    negative_prompt: str = Field(min_length=1, max_length=500)
    seed: int = Field(ge=0, le=18_446_744_073_709_551_615)
    denoise: float = Field(ge=0.45, le=0.65)
    width: int = Field(ge=512, le=1536, multiple_of=8)
    height: int = Field(ge=512, le=1536, multiple_of=8)
    downstream_consumer: Literal["blender.camera_backplate", "unreal.visual_target"]

    @model_validator(mode="after")
    def verify_identity(self) -> SceneConditioningRequest:
        payload = self.model_dump(mode="json", exclude={"request_id", "request_sha256"})
        expected = canonical_sha256(payload)
        if self.request_sha256 != expected or self.request_id != f"scene-condition-{expected[:16]}":
            raise ValueError("scene conditioning request identity is invalid")
        return self


def compile_scene_conditioning_request(
    *,
    scene_package_sha256: str,
    reference_beauty_sha256: str,
    conditioning_pass_sha256: str,
    conditioning_input_sha256: str,
    prompt: str,
    negative_prompt: str,
    seed: int,
) -> SceneConditioningRequest:
    payload = {
        "schema_id": "artflow-scene-conditioning-request/1",
        "scene_package_sha256": scene_package_sha256,
        "reference_beauty_sha256": reference_beauty_sha256,
        "conditioning_pass": "depth",
        "conditioning_pass_sha256": conditioning_pass_sha256,
        "conditioning_input_sha256": conditioning_input_sha256,
        "capability_id": "comfy.scene_depth_reference.flux2_klein.v1",
        "recipe_id": "composition-preserving-v1",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "seed": seed,
        "denoise": 0.65,
        "width": 1024,
        "height": 576,
        "downstream_consumer": "unreal.visual_target",
    }
    digest = canonical_sha256(payload)
    return SceneConditioningRequest(
        **payload,
        request_id=f"scene-condition-{digest[:16]}",
        request_sha256=digest,
    )
