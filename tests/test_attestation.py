import pytest

from artflow_agent.attestation import LocalCapabilityAttestation, attest_local_capability
from artflow_agent.contracts import ProviderCapabilityManifest
from artflow_agent.domain import EnvironmentSnapshot, RecipeDefinition


def _manifest() -> ProviderCapabilityManifest:
    return ProviderCapabilityManifest(
        provider_id="comfy-local",
        display_name="Local",
        execution_kind="local",
        privacy_class="local_only",
        cost_class="local_compute",
        requires_explicit_cost_approval=False,
        models=[
            {
                "model_id": "flux-local",
                "model_version": "1",
                "tasks": ["scene_direction"],
                "controls": ["reference_image"],
            }
        ],
    )


def _recipe() -> RecipeDefinition:
    return RecipeDefinition(
        recipe_id="reviewed-recipe",
        version="1",
        task_type="scene_direction",
        description="fixture",
        workflow_file="fixture.json",
        execution_ready=True,
        consumed_controls=["reference_image"],
        required_models=["model.safetensors"],
        required_nodes=["LoadImage", "SaveImage"],
        estimated_vram_mb=8000,
        slots=[],
    )


def test_supported_attestation_is_compact_and_independently_revalidated(tmp_path) -> None:
    snapshot = EnvironmentSnapshot(
        comfy_url="http://127.0.0.1:8188",
        reachable=True,
        comfyui_version="1.0",
        device_name="Fixture GPU",
        vram_mb=16000,
        nodes=["LoadImage", "SaveImage", "UnrelatedNode"],
        models=["model.safetensors", "other.safetensors"],
    )
    attestation = attest_local_capability(snapshot, _manifest(), "flux-local", _recipe())
    path = attestation.save(tmp_path / "attestation.json")

    assert attestation.status == "supported"
    assert attestation.observed_node_count == 3
    assert attestation.verified_models == ["model.safetensors"]
    assert LocalCapabilityAttestation.load_verified(path) == attestation
    assert len(path.read_bytes()) < 10_000


def test_missing_evidence_never_becomes_supported() -> None:
    missing = EnvironmentSnapshot(
        comfy_url="http://127.0.0.1:8188",
        reachable=True,
        vram_mb=4096,
        nodes=["LoadImage"],
        models=[],
    )
    unavailable = attest_local_capability(missing, _manifest(), "flux-local", _recipe())
    unknown = attest_local_capability(
        EnvironmentSnapshot(comfy_url="http://127.0.0.1:8188", reachable=False),
        _manifest(),
        "flux-local",
        _recipe(),
    )

    assert unavailable.status == "unsupported"
    assert "missing_node:SaveImage" in unavailable.reasons
    assert "missing_model:model.safetensors" in unavailable.reasons
    assert "insufficient_vram" in unavailable.reasons
    assert unknown.status == "unknown"
    assert unknown.reasons == ["runtime_unreachable"]


def test_tampered_saved_attestation_fails_verification(tmp_path) -> None:
    snapshot = EnvironmentSnapshot(
        comfy_url="http://127.0.0.1:8188",
        reachable=True,
        vram_mb=16000,
        nodes=["LoadImage", "SaveImage"],
        models=["model.safetensors"],
    )
    path = attest_local_capability(
        snapshot, _manifest(), "flux-local", _recipe()
    ).save(tmp_path / "attestation.json")
    content = path.read_text(encoding="utf-8").replace('"vram_mb": 16000', '"vram_mb": 1')
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="fingerprint does not match"):
        LocalCapabilityAttestation.load_verified(path)


def test_recipe_cannot_consume_a_control_the_manifest_does_not_declare() -> None:
    snapshot = EnvironmentSnapshot(
        comfy_url="http://127.0.0.1:8188",
        reachable=True,
        vram_mb=16000,
        nodes=["LoadImage", "SaveImage"],
        models=["model.safetensors"],
    )
    recipe = _recipe().model_copy(
        update={"consumed_controls": ["reference_image", "depth"]}
    )

    attestation = attest_local_capability(snapshot, _manifest(), "flux-local", recipe)

    assert attestation.status == "unsupported"
    assert "control_not_declared:depth" in attestation.reasons
