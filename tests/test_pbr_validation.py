from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from artflow_agent.pbr_validation import (
    PBRGenerationValidationReceipt,
    inspect_pbr_channel,
    synthesize_dielectric_texture_set,
    validate_generation,
)


def save(path: Path, color: tuple[int, int, int]) -> Path:
    Image.new("RGB", (512, 512), color).save(path)
    return path


def test_normal_channel_rejects_non_normal_scene_pixels(tmp_path: Path) -> None:
    artifact = inspect_pbr_channel(
        "normal", save(tmp_path / "normal.png", (120, 115, 110)), expected_size=(512, 512)
    )
    assert artifact.accepted is False
    assert "normal_blue_axis_missing" in artifact.rejection_reasons


def test_scalar_channel_rejects_colored_pixels(tmp_path: Path) -> None:
    artifact = inspect_pbr_channel(
        "roughness", save(tmp_path / "roughness.png", (20, 90, 210)), expected_size=(512, 512)
    )
    assert artifact.accepted is False
    assert "scalar_map_contains_color" in artifact.rejection_reasons


def test_receipt_cannot_claim_validated_when_artifact_failed(tmp_path: Path) -> None:
    artifact = inspect_pbr_channel(
        "normal", save(tmp_path / "normal.png", (120, 115, 110)), expected_size=(512, 512)
    )
    artifacts = [
        artifact.model_copy(update={"channel": channel})
        for channel in (
            "base_color",
            "normal",
            "roughness",
            "metallic",
            "ambient_occlusion",
        )
    ]
    with pytest.raises(ValidationError, match="status"):
        PBRGenerationValidationReceipt(
            prompt_id="prompt-123",
            request_id="pbr-" + "a" * 24,
            workflow_sha256="b" * 64,
            capability_snapshot_sha256="c" * 64,
            execution_seconds=1,
            artifacts=artifacts,
            status="validated",
        )


def test_dielectric_synthesizer_produces_aligned_valid_contract(tmp_path: Path) -> None:
    base = tmp_path / "base.png"
    image = Image.new("RGB", (512, 512))
    image.putdata(
        [
            (
                (x + y) % 128 + 40,
                (x * 2 + y) % 128 + 40,
                (x + y * 2) % 128 + 40,
            )
            for y in range(512)
            for x in range(512)
        ]
    )
    image.save(base)
    paths = synthesize_dielectric_texture_set(base, tmp_path / "normalized")
    receipt = validate_generation(
        prompt_id="prompt-technical",
        request_id="pbr-" + "a" * 24,
        workflow_sha256="b" * 64,
        capability_snapshot_sha256="c" * 64,
        execution_seconds=1,
        paths=paths,
        expected_size=(512, 512),
    )
    assert receipt.status == "validated"
    metallic = next(item for item in receipt.artifacts if item.channel == "metallic")
    assert metallic.metrics.source_mode == "L"
