from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import httpx
from pydantic import ValidationError

from artflow_agent.comfy import _validate_workflow_against_object_info
from artflow_agent.pbr import (
    ComfyCapabilitySnapshot,
    CompiledPBRWorkflow,
    PBRBoundaryError,
    PBRCompileRequest,
    PBRWorkflowCompiler,
    canonical_sha256,
    capture_capability_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently verify the M8 PBR graph compilation.")
    parser.add_argument("evidence_dir", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8190")
    parser.add_argument("--shared-endpoint", default="http://127.0.0.1:8188")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    root = args.evidence_dir
    snapshot = ComfyCapabilitySnapshot.model_validate_json(
        (root / "comfy-capability-snapshot.json").read_text(encoding="utf-8")
    )
    compiled = CompiledPBRWorkflow.model_validate_json(
        (root / "compiled-pbr-workflow.json").read_text(encoding="utf-8")
    )
    compiler = PBRWorkflowCompiler(
        ROOT / "recipes/pbr-material-v1.template.json",
        ROOT / "recipes/pbr-material-v1.workflow.json",
    )
    with httpx.Client(base_url=args.endpoint, timeout=20) as client:
        stats = client.get("/system_stats").json()
        object_info = client.get("/object_info").json()
    with httpx.Client(base_url=args.shared_endpoint, timeout=20) as client:
        shared_info = client.get("/object_info").json()
    replayed = capture_capability_snapshot(
        endpoint=args.endpoint,
        system_stats=stats,
        object_info=object_info,
        required_nodes=compiler.template.required_nodes,
        production_nodes_commit=snapshot.production_nodes_commit,
        production_nodes_license_sha256=snapshot.production_nodes_license_sha256,
        captured_at=snapshot.captured_at,
    )
    assert replayed.snapshot_sha256 == snapshot.snapshot_sha256
    assert compiled.capability_snapshot_sha256 == snapshot.snapshot_sha256
    assert not _validate_workflow_against_object_info(compiled.workflow, object_info)
    assert len(compiled.workflow) == 49
    assert {item.channel for item in compiled.texture_set.channels} == {
        "base_color", "normal", "roughness", "metallic", "ambient_occlusion"
    }
    assert compiled.workflow["26"]["inputs"]["filename_prefix"].startswith(
        "ArtFlow/PBR/ruin_altar_basalt/"
    )

    negative_controls: dict[str, bool] = {}
    try:
        PBRCompileRequest.model_validate(
            {
                "material_id": "ruin_altar_basalt",
                "source_image": "../../company-secret.png",
                "source_sha256": "a" * 64,
                "visual_intent": "weathered basalt material surface",
                "negative_prompt": "text",
                "seed": 1,
                "denoise": 0.4,
                "width": 1024,
                "height": 1024,
                "class_type": "PythonScript",
            }
        )
    except ValidationError:
        negative_controls["path_escape_and_class_injection_rejected"] = True
    else:
        raise AssertionError("unsafe request was accepted")

    tampered = json.loads((ROOT / "recipes/pbr-material-v1.workflow.json").read_text())
    tampered["1"]["class_type"] = "PythonScript"
    with tempfile.TemporaryDirectory(prefix="artflow-pbr-negative-") as temporary_dir:
        temporary_root = Path(temporary_dir)
        temporary_workflow = temporary_root / "pbr-material-v1.workflow.json"
        temporary_manifest = temporary_root / "pbr-material-v1.template.json"
        temporary_workflow.write_text(
            json.dumps(tampered, ensure_ascii=False), encoding="utf-8"
        )
        temporary_manifest.write_bytes(
            (ROOT / "recipes/pbr-material-v1.template.json").read_bytes()
        )
        try:
            PBRWorkflowCompiler(temporary_manifest, temporary_workflow)
        except PBRBoundaryError as exc:
            assert "hash" in str(exc)
            negative_controls["tampered_topology_rejected"] = True
        else:
            raise AssertionError("tampered workflow topology was accepted")

    drifted_facts = snapshot.model_dump(mode="json", exclude={"snapshot_sha256"})
    drifted_facts["required_nodes"][0]["schema_sha256"] = "f" * 64
    drifted_facts["snapshot_sha256"] = canonical_sha256(drifted_facts)
    drifted = ComfyCapabilitySnapshot.model_validate(drifted_facts)
    fixture_request = PBRCompileRequest.model_validate(
        {
            "material_id": "ruin_altar_basalt",
            "source_image": "ArtFlow/M7/candidate-beauty.png",
            "source_sha256": "a" * 64,
            "visual_intent": "weathered basalt material surface",
            "negative_prompt": "text",
            "seed": 1,
            "denoise": 0.4,
            "width": 1024,
            "height": 1024,
        }
    )
    try:
        compiler.compile(fixture_request, drifted)
    except PBRBoundaryError as exc:
        assert "schemas drifted" in str(exc)
        negative_controls["node_schema_drift_rejected"] = True
    else:
        raise AssertionError("node schema drift was accepted")

    result = {
        "schema_id": "pbr-compilation-verification/1",
        "verified": True,
        "snapshot_sha256": snapshot.snapshot_sha256,
        "workflow_sha256": compiled.workflow_sha256,
        "node_count": snapshot.observed_node_count,
        "required_node_count": len(snapshot.required_nodes),
        "texture_channel_count": len(compiled.texture_set.channels),
        "negative_controls": negative_controls,
        "shared_host_node_count": len(shared_info),
        "production_nodes_missing_on_shared_host": sorted(
            {
                "GenerationReceipt",
                "ProductionConstraintCheck",
                "WorkflowContractCheck",
            }
            - set(shared_info)
        ),
        "compiled_artifact_sha256": hashlib.sha256(
            (root / "compiled-pbr-workflow.json").read_bytes()
        ).hexdigest(),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(rendered, encoding="utf-8")
        temporary.replace(args.output)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
