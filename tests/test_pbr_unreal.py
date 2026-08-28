from __future__ import annotations

import pytest
from pydantic import ValidationError

from artflow_agent.pbr import canonical_sha256
from artflow_agent.pbr_unreal import UnrealPBRReturnRequest


def request_facts() -> dict[str, object]:
    textures = [
        {
            "channel": channel,
            "path": f"artifacts/goal/m8-s2-pbr-material/validated/{filename}",
            "sha256": str(index) * 64,
            "color_space": "srgb" if channel == "base_color" else "linear",
            "pixel_format": "rgb8" if channel in {"base_color", "normal"} else "gray8",
        }
        for index, (channel, filename) in enumerate(
            [
                ("base_color", "base.png"),
                ("normal", "normal.png"),
                ("roughness", "roughness.png"),
                ("metallic", "metallic.png"),
                ("ambient_occlusion", "ao.png"),
            ],
            start=1,
        )
    ]
    facts: dict[str, object] = {
        "schema_id": "unreal-pbr-return-request/1",
        "request_id": "pbr-ue-" + "a" * 24,
        "generation_receipt_sha256": "b" * 64,
        "source_scene_sha256": "c" * 64,
        "authority_scope": "project_local_unreal_fixture",
        "destination_scene_path": "/Game/ArtFlow/Staging/AF_cb2176a7a45bbad1",
        "destination_root": "/Game/ArtFlow/Generated/" + "d" * 16,
        "target_actor_label": "Editable_Form",
        "material_instance_name": "MI_RuinAltarBasalt",
        "textures": textures,
    }
    facts["request_sha256"] = canonical_sha256(facts)
    return facts


def test_unreal_pbr_request_accepts_exact_five_channel_boundary() -> None:
    request = UnrealPBRReturnRequest.model_validate(request_facts())
    assert len(request.textures) == 5


def test_unreal_pbr_request_rejects_destination_or_hash_tamper() -> None:
    facts = request_facts()
    facts["destination_root"] = "/Game/Company/Secret"
    with pytest.raises(ValidationError):
        UnrealPBRReturnRequest.model_validate(facts)
    facts = request_facts()
    facts["target_actor_label"] = "Protected_Blockout"
    with pytest.raises(ValidationError):
        UnrealPBRReturnRequest.model_validate(facts)
