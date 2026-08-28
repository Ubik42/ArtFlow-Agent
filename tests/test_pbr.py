from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.pbr import (
    ComfyCapabilitySnapshot,
    PBRBoundaryError,
    PBRCompileRequest,
    PBRWorkflowCompiler,
    canonical_sha256,
    capture_capability_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]


def compiler() -> PBRWorkflowCompiler:
    return PBRWorkflowCompiler(
        ROOT / "recipes/pbr-material-v1.template.json",
        ROOT / "recipes/pbr-material-v1.workflow.json",
    )


def capability_snapshot() -> ComfyCapabilitySnapshot:
    template = compiler().template
    facts = {
        "schema_id": "comfy-capability-snapshot/1",
        "snapshot_id": "comfy-pbr-fixture",
        "captured_at": "2026-08-28T00:00:00Z",
        "endpoint": "http://127.0.0.1:8190",
        "comfyui_version": "0.28.0",
        "python_version": "3.12",
        "pytorch_version": "2.13",
        "device_name": "fixture",
        "observed_node_count": len(template.required_nodes),
        "required_nodes": [
            {
                "class_type": name,
                "schema_sha256": template.required_node_schema_sha256[name],
                "python_module": "fixture",
                "output_types": ["FIXTURE"],
            }
            for name in sorted(template.required_nodes)
        ],
        "missing_nodes": [],
        "production_nodes_commit": "d102528",
        "production_nodes_license": "MIT",
        "production_nodes_license_sha256": "a" * 64,
    }
    facts["snapshot_sha256"] = canonical_sha256(facts)
    return ComfyCapabilitySnapshot.model_validate(facts)


def request(**updates: object) -> PBRCompileRequest:
    values: dict[str, object] = {
        "material_id": "ruin_stone",
        "source_image": "ArtFlow/M7/beauty.png",
        "source_sha256": "b" * 64,
        "visual_intent": "weathered basalt stone with subtle mineral veins",
        "negative_prompt": "text, watermark, baked lighting",
        "seed": 240827,
        "denoise": 0.45,
        "width": 1024,
        "height": 1024,
    }
    values.update(updates)
    return PBRCompileRequest.model_validate(values)


def test_reviewed_pbr_template_compiles_exact_five_channel_contract() -> None:
    first = compiler().compile(request(), capability_snapshot())
    second = compiler().compile(request(), capability_snapshot())

    assert first.request_id == second.request_id
    assert first.workflow_sha256 == second.workflow_sha256
    assert len(first.workflow) == 49
    assert [item.channel for item in first.texture_set.channels] == [
        "base_color",
        "normal",
        "roughness",
        "metallic",
        "ambient_occlusion",
    ]
    assert first.workflow["36"]["inputs"]["filename_prefix"] == (
        "ArtFlow/PBR/ruin_stone/ruin_stone_normal"
    )
    assert first.workflow["12"]["inputs"]["width"] == 1024


def test_request_rejects_path_escape_and_arbitrary_graph_fields() -> None:
    with pytest.raises(ValidationError):
        request(source_image="../../secret.png")
    with pytest.raises(ValidationError):
        PBRCompileRequest.model_validate({**request().model_dump(), "class_type": "PythonScript"})


def test_template_hash_and_filename_are_a_fail_closed_boundary(tmp_path: Path) -> None:
    source = json.loads((ROOT / "recipes/pbr-material-v1.workflow.json").read_text())
    source["1"]["class_type"] = "PythonScript"
    tampered = tmp_path / "pbr-material-v1.workflow.json"
    tampered.write_text(json.dumps(source), encoding="utf-8")
    manifest = tmp_path / "pbr-material-v1.template.json"
    manifest.write_bytes((ROOT / "recipes/pbr-material-v1.template.json").read_bytes())

    with pytest.raises(PBRBoundaryError, match="hash"):
        PBRWorkflowCompiler(manifest, tampered)


def test_capability_snapshot_rejects_missing_or_tampered_node_evidence() -> None:
    snapshot = capability_snapshot()
    with pytest.raises(ValidationError, match="fingerprint"):
        ComfyCapabilitySnapshot.model_validate(
            {**snapshot.model_dump(mode="json"), "observed_node_count": 1}
        )
    with pytest.raises(PBRBoundaryError, match="Missing required"):
        capture_capability_snapshot(
            endpoint="http://127.0.0.1:8190",
            system_stats={"system": {}, "devices": []},
            object_info={},
            required_nodes=["GenerationReceipt"],
            production_nodes_commit="d102528",
            production_nodes_license_sha256="a" * 64,
            captured_at=datetime(2026, 8, 28, tzinfo=UTC),
        )


def test_compiler_rejects_reviewed_node_schema_drift() -> None:
    snapshot = capability_snapshot()
    facts = snapshot.model_dump(mode="json", exclude={"snapshot_sha256"})
    facts["required_nodes"][0]["schema_sha256"] = "f" * 64
    facts["snapshot_sha256"] = canonical_sha256(facts)
    drifted = ComfyCapabilitySnapshot.model_validate(facts)

    with pytest.raises(PBRBoundaryError, match="schemas drifted"):
        compiler().compile(request(), drifted)
