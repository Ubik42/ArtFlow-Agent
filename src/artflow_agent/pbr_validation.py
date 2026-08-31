from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from PIL import Image, ImageFilter, ImageOps, ImageStat
from pydantic import BaseModel, ConfigDict, Field, model_validator

from artflow_agent.pbr import REQUIRED_PBR_CHANNELS, SHA256_PATTERN


class PBRValidationError(RuntimeError):
    """Raised when provider pixels cannot be admitted as technical PBR maps."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ChannelMetrics(StrictModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    source_mode: str
    rgb_mean: tuple[float, float, float]
    rgb_stddev: tuple[float, float, float]
    chroma_error: float = Field(ge=0, le=1)
    seam_error: float = Field(ge=0, le=1)
    normal_blue_dominance: float = Field(ge=-1, le=1)
    normal_unit_error: float = Field(ge=0)


class PBRRawArtifact(StrictModel):
    channel: Literal["base_color", "normal", "roughness", "metallic", "ambient_occlusion"]
    relative_path: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    byte_count: int = Field(gt=0)
    metrics: ChannelMetrics
    accepted: bool
    rejection_reasons: list[str]


class PBRGenerationValidationReceipt(StrictModel):
    schema_id: Literal["pbr-generation-validation-receipt/1"] = (
        "pbr-generation-validation-receipt/1"
    )
    prompt_id: str = Field(min_length=8)
    request_id: str = Field(pattern=r"^pbr-[0-9a-f]{24}$")
    workflow_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_seconds: float = Field(gt=0)
    artifacts: list[PBRRawArtifact] = Field(min_length=5, max_length=5)
    status: Literal["validated", "semantic_invalid"]

    @model_validator(mode="after")
    def validate_set(self) -> PBRGenerationValidationReceipt:
        channels = [item.channel for item in self.artifacts]
        if len(set(channels)) != 5 or set(channels) != set(REQUIRED_PBR_CHANNELS):
            raise ValueError("receipt must cover each PBR channel exactly once")
        expected = "validated" if all(item.accepted for item in self.artifacts) else "semantic_invalid"
        if self.status != expected:
            raise ValueError("receipt status does not match artifact validation")
        return self


def inspect_pbr_channel(
    channel: str,
    path: Path,
    *,
    expected_size: tuple[int, int],
) -> PBRRawArtifact:
    if channel not in REQUIRED_PBR_CHANNELS:
        raise PBRValidationError(f"Unknown PBR channel: {channel}")
    try:
        with Image.open(path) as source:
            source.load()
            width, height = source.size
            source_mode = source.mode
            sample = source.convert("RGB")
    except (OSError, ValueError) as exc:
        raise PBRValidationError(f"Undecodable PBR artifact: {path.name}") from exc
    sample.thumbnail((256, 256), Image.Resampling.LANCZOS)
    stats = ImageStat.Stat(sample)
    means = tuple(round(value / 255.0, 6) for value in stats.mean[:3])
    stddev = tuple(round(value / 255.0, 6) for value in stats.stddev[:3])
    pixels = list(sample.get_flattened_data())
    chroma_error = sum(max(pixel) - min(pixel) for pixel in pixels) / (255.0 * len(pixels))
    normal_blue_dominance = sum(
        pixel[2] - ((pixel[0] + pixel[1]) / 2.0) for pixel in pixels
    ) / (255.0 * len(pixels))
    normal_unit_error = sum(
        abs(
            (((pixel[0] / 127.5) - 1.0) ** 2 + ((pixel[1] / 127.5) - 1.0) ** 2 + ((pixel[2] / 127.5) - 1.0) ** 2) ** 0.5
            - 1.0
        )
        for pixel in pixels
    ) / len(pixels)
    seam_error = _seam_error(sample)
    reasons: list[str] = []
    if (width, height) != expected_size:
        reasons.append(f"dimension_mismatch:{width}x{height}")
    if channel == "normal":
        if normal_blue_dominance < 0.08:
            reasons.append("normal_blue_axis_missing")
        if normal_unit_error > 0.35:
            reasons.append("normal_vectors_not_unit_like")
    elif channel in {"roughness", "metallic", "ambient_occlusion"}:
        if source_mode != "L":
            reasons.append("scalar_map_not_gray8")
        if chroma_error > 0.035:
            reasons.append("scalar_map_contains_color")
        if channel == "metallic" and max(means) > 0.05:
            reasons.append("dielectric_metallic_not_black")
        if channel != "metallic" and max(stddev) < 0.015:
            reasons.append("scalar_map_has_no_signal")
    elif seam_error > 0.22:
        reasons.append("base_color_not_tileable")
    return PBRRawArtifact(
        channel=channel,
        relative_path=path.name,
        sha256=_sha256(path),
        byte_count=path.stat().st_size,
        metrics=ChannelMetrics(
            width=width,
            height=height,
            source_mode=source_mode,
            rgb_mean=means,
            rgb_stddev=stddev,
            chroma_error=round(chroma_error, 6),
            seam_error=round(seam_error, 6),
            normal_blue_dominance=round(normal_blue_dominance, 6),
            normal_unit_error=round(normal_unit_error, 6),
        ),
        accepted=not reasons,
        rejection_reasons=reasons,
    )


def validate_generation(
    *,
    prompt_id: str,
    request_id: str,
    workflow_sha256: str,
    capability_snapshot_sha256: str,
    execution_seconds: float,
    paths: dict[str, Path],
    expected_size: tuple[int, int],
) -> PBRGenerationValidationReceipt:
    if set(paths) != set(REQUIRED_PBR_CHANNELS):
        raise PBRValidationError("exactly five named PBR channel paths are required")
    artifacts = [
        inspect_pbr_channel(channel, paths[channel], expected_size=expected_size)
        for channel in REQUIRED_PBR_CHANNELS
    ]
    return PBRGenerationValidationReceipt(
        prompt_id=prompt_id,
        request_id=request_id,
        workflow_sha256=workflow_sha256,
        capability_snapshot_sha256=capability_snapshot_sha256,
        execution_seconds=execution_seconds,
        artifacts=artifacts,
        status="validated" if all(item.accepted for item in artifacts) else "semantic_invalid",
    )


def synthesize_dielectric_texture_set(
    base_color: Path,
    output_root: Path,
    *,
    material_id: str = "ruin_altar_basalt",
) -> dict[str, Path]:
    """Build spatially aligned technical maps from an accepted dielectric albedo candidate."""
    output_root.mkdir(parents=True, exist_ok=True)
    with Image.open(base_color) as source:
        albedo = _seamless_edges(source.convert("RGB"))
    paths = {
        "base_color": output_root / f"{material_id}_base_color.png",
        "normal": output_root / f"{material_id}_normal_dx.png",
        "roughness": output_root / f"{material_id}_roughness.png",
        "metallic": output_root / f"{material_id}_metallic.png",
        "ambient_occlusion": output_root / f"{material_id}_ao.png",
    }
    albedo.save(paths["base_color"], compress_level=6)
    height = ImageOps.autocontrast(albedo.convert("L"), cutoff=1)
    gradient_x = height.filter(
        ImageFilter.Kernel((3, 3), (-1, 0, 1, -2, 0, 2, -1, 0, 1), scale=12, offset=128)
    )
    gradient_y = height.filter(
        ImageFilter.Kernel((3, 3), (-1, -2, -1, 0, 0, 0, 1, 2, 1), scale=12, offset=128)
    )
    blue = Image.new("L", albedo.size, 245)
    Image.merge("RGB", (gradient_x, ImageOps.invert(gradient_y), blue)).save(
        paths["normal"], compress_level=6
    )
    roughness = height.point(lambda value: 165 + (value * 70 // 255))
    roughness.save(paths["roughness"], compress_level=6)
    Image.new("L", albedo.size, 0).save(paths["metallic"], compress_level=6)
    ao_source = height.filter(ImageFilter.GaussianBlur(radius=3))
    ao = ao_source.point(lambda value: 70 + (value * 185 // 255))
    ao.save(paths["ambient_occlusion"], compress_level=6)
    return paths


def _seamless_edges(image: Image.Image, border: int = 24) -> Image.Image:
    """Blend opposite borders without changing the generated interior."""
    result = image.copy()
    pixels = result.load()
    width, height = result.size
    border = max(1, min(border, width // 8, height // 8))
    for offset in range(border):
        weight = (border - offset) / border
        left_x, right_x = offset, width - 1 - offset
        for y in range(height):
            left, right = pixels[left_x, y], pixels[right_x, y]
            average = tuple((left[channel] + right[channel]) // 2 for channel in range(3))
            pixels[left_x, y] = tuple(
                round(left[channel] * (1 - weight) + average[channel] * weight)
                for channel in range(3)
            )
            pixels[right_x, y] = tuple(
                round(right[channel] * (1 - weight) + average[channel] * weight)
                for channel in range(3)
            )
    for offset in range(border):
        weight = (border - offset) / border
        top_y, bottom_y = offset, height - 1 - offset
        for x in range(width):
            top, bottom = pixels[x, top_y], pixels[x, bottom_y]
            average = tuple((top[channel] + bottom[channel]) // 2 for channel in range(3))
            pixels[x, top_y] = tuple(
                round(top[channel] * (1 - weight) + average[channel] * weight)
                for channel in range(3)
            )
            pixels[x, bottom_y] = tuple(
                round(bottom[channel] * (1 - weight) + average[channel] * weight)
                for channel in range(3)
            )
    return result


def _seam_error(image: Image.Image) -> float:
    width, height = image.size
    pixels = image.load()
    vertical = sum(
        abs(pixels[0, y][channel] - pixels[width - 1, y][channel])
        for y in range(height)
        for channel in range(3)
    ) / (height * 3 * 255.0)
    horizontal = sum(
        abs(pixels[x, 0][channel] - pixels[x, height - 1][channel])
        for x in range(width)
        for channel in range(3)
    ) / (width * 3 * 255.0)
    return (vertical + horizontal) / 2.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
