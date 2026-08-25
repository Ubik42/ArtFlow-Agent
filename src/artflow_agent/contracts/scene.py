from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath, PureWindowsPath
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ArtifactRef(BaseModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = Field(min_length=3)

    @field_validator("path")
    @classmethod
    def require_portable_relative_path(cls, value: str) -> str:
        normalized = value.strip().replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not normalized
            or path.is_absolute()
            or PureWindowsPath(normalized).is_absolute()
            or ".." in path.parts
        ):
            raise ValueError("artifact path must be portable and package-relative")
        return path.as_posix()


class CameraConstraint(BaseModel):
    projection: Literal["perspective", "orthographic"]
    world_transform: list[float] = Field(min_length=16, max_length=16)
    horizontal_fov_degrees: float | None = Field(default=None, gt=0, lt=180)
    ortho_width: float | None = Field(default=None, gt=0)
    near_clip: float = Field(gt=0)
    far_clip: float = Field(gt=0)
    width: int = Field(ge=64, le=16384)
    height: int = Field(ge=64, le=16384)

    @model_validator(mode="after")
    def validate_projection_parameters(self) -> CameraConstraint:
        if self.near_clip >= self.far_clip:
            raise ValueError("near_clip must be smaller than far_clip")
        if self.projection == "perspective" and self.horizontal_fov_degrees is None:
            raise ValueError("perspective cameras require horizontal_fov_degrees")
        if self.projection == "orthographic" and self.ortho_width is None:
            raise ValueError("orthographic cameras require ortho_width")
        return self


RenderPassKind = Literal[
    "beauty",
    "depth",
    "world_normal",
    "object_id",
    "editable_mask",
    "protected_mask",
]


class RenderPass(BaseModel):
    kind: RenderPassKind
    artifact: ArtifactRef
    encoding: str = Field(min_length=1)


class RegionConstraint(BaseModel):
    region_id: str = Field(min_length=1, max_length=120)
    mode: Literal["protected", "editable"]
    object_ids: list[str] = Field(min_length=1)


class ArtIntent(BaseModel):
    goal: str = Field(min_length=10, max_length=1600)
    preserve: list[str] = Field(default_factory=list)
    prohibit: list[str] = Field(default_factory=list)
    reference_assets: list[ArtifactRef] = Field(default_factory=list, max_length=8)


class SourceProvenance(BaseModel):
    application: str = Field(min_length=1)
    application_version: str = Field(min_length=1)
    project_name: str = Field(min_length=1)
    scene_name: str = Field(min_length=1)
    captured_at: datetime


class DeliveryRequirements(BaseModel):
    color_space: str = Field(min_length=1)
    file_format: Literal["png", "exr", "tiff"]
    purpose: Literal["art_direction", "review_texture", "concept_reference"]


class SceneConstraintPackage(BaseModel):
    schema_id: Literal["scene-constraint-package/1"] = "scene-constraint-package/1"
    package_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    camera: CameraConstraint
    passes: list[RenderPass] = Field(min_length=4)
    regions: list[RegionConstraint] = Field(default_factory=list)
    art_intent: ArtIntent
    provenance: SourceProvenance
    delivery: DeliveryRequirements

    @model_validator(mode="after")
    def require_unique_production_passes(self) -> SceneConstraintPackage:
        kinds = [item.kind for item in self.passes]
        if len(kinds) != len(set(kinds)):
            raise ValueError("render pass kinds must be unique")
        required = {"beauty", "depth", "world_normal", "object_id"}
        missing = sorted(required - set(kinds))
        if missing:
            raise ValueError(f"missing required render passes: {', '.join(missing)}")
        region_ids = [item.region_id for item in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("region IDs must be unique")
        return self

