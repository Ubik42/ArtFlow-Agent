from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from artflow_agent.pbr import REQUIRED_PBR_CHANNELS, SHA256_PATTERN, canonical_sha256


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UnrealPBRTextureInput(StrictModel):
    channel: Literal["base_color", "normal", "roughness", "metallic", "ambient_occlusion"]
    path: str = Field(pattern=r"^artifacts/goal/[A-Za-z0-9_.-]+/validated/[A-Za-z0-9_.-]+\.png$")
    sha256: str = Field(pattern=SHA256_PATTERN)
    color_space: Literal["srgb", "linear"]
    pixel_format: Literal["rgb8", "gray8"]


class UnrealPBRReturnRequest(StrictModel):
    schema_id: Literal["unreal-pbr-return-request/1"] = "unreal-pbr-return-request/1"
    request_id: str = Field(pattern=r"^pbr-ue-[0-9a-f]{24}$")
    generation_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_scene_sha256: str = Field(pattern=SHA256_PATTERN)
    authority_scope: Literal["project_local_unreal_fixture"]
    destination_scene_path: str = Field(pattern=r"^/Game/ArtFlow/Staging/[A-Za-z0-9_]+$")
    destination_root: str = Field(pattern=r"^/Game/ArtFlow/Generated/[0-9a-f]{16}$")
    target_actor_label: Literal["Editable_Form"]
    material_instance_name: str = Field(pattern=r"^MI_[A-Za-z0-9_]{3,64}$")
    textures: list[UnrealPBRTextureInput] = Field(min_length=5, max_length=5)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_request(self) -> UnrealPBRReturnRequest:
        if {item.channel for item in self.textures} != set(REQUIRED_PBR_CHANNELS):
            raise ValueError("request must bind every PBR channel exactly once")
        if self.request_sha256 != canonical_sha256(
            self.model_dump(mode="json", exclude={"request_sha256"})
        ):
            raise ValueError("Unreal PBR request fingerprint mismatch")
        return self


class UnrealPBRReturnReceipt(StrictModel):
    schema_id: Literal["unreal-pbr-return-receipt/1"] = "unreal-pbr-return-receipt/1"
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    status: Literal["imported", "reconciled"]
    engine_version: str
    destination_scene_path: str
    target_actor_label: str
    imported_texture_paths: dict[str, str]
    master_material_path: str
    material_instance_path: str
    source_scene_sha256_before: str = Field(pattern=SHA256_PATTERN)
    source_scene_sha256_after: str = Field(pattern=SHA256_PATTERN)
    protected_state_before: str = Field(pattern=SHA256_PATTERN)
    protected_state_after: str = Field(pattern=SHA256_PATTERN)
    candidate_render_path: str
    candidate_render_sha256: str = Field(pattern=SHA256_PATTERN)
    completed_at: str
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_receipt(self) -> UnrealPBRReturnReceipt:
        if self.source_scene_sha256_before != self.source_scene_sha256_after:
            raise ValueError("source scene changed during PBR return")
        if self.protected_state_before != self.protected_state_after:
            raise ValueError("protected actor changed during PBR return")
        if set(self.imported_texture_paths) != set(REQUIRED_PBR_CHANNELS):
            raise ValueError("receipt does not cover all texture channels")
        if self.receipt_sha256 != canonical_sha256(
            self.model_dump(mode="json", exclude={"receipt_sha256"})
        ):
            raise ValueError("Unreal PBR receipt fingerprint mismatch")
        return self


def build_unreal_pbr_request(
    *,
    receipt_path: Path,
    texture_root: Path,
    source_scene: Path,
    repo_root: Path,
    material_id: str = "ruin_altar_basalt",
    destination_scene_path: str = "/Game/ArtFlow/Staging/AF_cb2176a7a45bbad1",
    material_instance_name: str = "MI_RuinAltarBasalt",
) -> UnrealPBRReturnRequest:
    generation_sha = _sha256(receipt_path)
    specs = {
        "base_color": (f"{material_id}_base_color.png", "srgb", "rgb8"),
        "normal": (f"{material_id}_normal_dx.png", "linear", "rgb8"),
        "roughness": (f"{material_id}_roughness.png", "linear", "gray8"),
        "metallic": (f"{material_id}_metallic.png", "linear", "gray8"),
        "ambient_occlusion": (f"{material_id}_ao.png", "linear", "gray8"),
    }
    textures = []
    for channel, (filename, color_space, pixel_format) in specs.items():
        path = texture_root / filename
        textures.append(
            UnrealPBRTextureInput(
                channel=channel,
                path=path.resolve().relative_to(repo_root.resolve()).as_posix(),
                sha256=_sha256(path),
                color_space=color_space,
                pixel_format=pixel_format,
            )
        )
    identity = canonical_sha256([generation_sha, [item.sha256 for item in textures]])[:24]
    destination_id = identity[:16]
    facts = {
        "schema_id": "unreal-pbr-return-request/1",
        "request_id": f"pbr-ue-{identity}",
        "generation_receipt_sha256": generation_sha,
        "source_scene_sha256": _sha256(source_scene),
        "authority_scope": "project_local_unreal_fixture",
        "destination_scene_path": destination_scene_path,
        "destination_root": f"/Game/ArtFlow/Generated/{destination_id}",
        "target_actor_label": "Editable_Form",
        "material_instance_name": material_instance_name,
        "textures": [item.model_dump(mode="json") for item in textures],
    }
    facts["request_sha256"] = canonical_sha256(facts)
    return UnrealPBRReturnRequest.model_validate(facts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
