from __future__ import annotations

import json
from pathlib import Path

from artflow_agent.provenance import (
    EvidenceBinding,
    ProvenanceManifest,
    UnrealReturnReceipt,
    UnrealReturnRequest,
    canonical_sha256,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "artifacts/goal/m6-s1-unreal-return"


def binding(role: str, relative: str, media_type: str) -> EvidenceBinding:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise RuntimeError(f"Missing or escaped provenance ingredient: {role}")
    return EvidenceBinding(
        role=role,
        path=path.relative_to(ROOT).as_posix(),
        sha256=sha256_file(path),
        media_type=media_type,
    )


def main() -> None:
    request = UnrealReturnRequest.model_validate_json(
        (OUTPUT_ROOT / "unreal-return-request.json").read_text(encoding="utf-8")
    )
    receipt = UnrealReturnReceipt.model_validate_json(
        (OUTPUT_ROOT / "unreal-return-receipt.json").read_text(encoding="utf-8")
    )
    ingredients = [
        binding(
            "source_scene_package",
            "artifacts/goal/m3-s10-real-unreal-scene-package.zip",
            "application/zip",
        ),
        binding(
            "deterministic_tribunal",
            "artifacts/goal/m4-s1-tribunal/tribunal-report.json",
            "application/json",
        ),
        binding(
            "multimodal_tribunal",
            "artifacts/goal/m4-s2-negative-control/multimodal-tribunal-report.json",
            "application/json",
        ),
        binding(
            "adoption_decision",
            "artifacts/goal/m4-s3-bounded-revision/adoption-decision.json",
            "application/json",
        ),
        binding(
            "bounded_revision_request",
            "artifacts/goal/m4-s3-bounded-revision/revision-request.json",
            "application/json",
        ),
        binding(
            "bounded_revision_result",
            "artifacts/goal/m4-s3-bounded-revision/bounded-revision-result.json",
            "application/json",
        ),
        binding(
            "agent_harness_scorecard",
            "artifacts/goal/m5-s3-harness/harness-scorecard.json",
            "application/json",
        ),
        binding(
            "unreal_visible_verification",
            "artifacts/goal/m6-s1-unreal-return/unreal-return-visible.png",
            "image/png",
        ),
    ]
    payload = {
        "schema_id": "artflow-c2pa-compatible-provenance/1",
        "c2pa_reference_version": "2.4.0",
        "conformance": "compatible_unsigned_sidecar",
        "claim_generator_info": {
            "name": "ArtFlow Agent",
            "version": "0.1.0",
            "specVersion": "2.4.0",
        },
        "instance_id": f"urn:artflow:{request.import_id}",
        "title": "ArtFlow verified Unreal return",
        "output": request.source.model_dump(mode="json"),
        "ingredients": [item.model_dump(mode="json") for item in ingredients],
        "assertions": {
            "c2pa.hash.data": {
                "alg": "sha256",
                "hash": request.source.sha256,
                "binding_scope": "entire external output asset",
            },
            "c2pa.actions.v2": {
                "actions": [
                    {
                        "action": "c2pa.opened",
                        "parameters": {"ingredients": ["adoption_decision"]},
                    },
                    {
                        "action": "c2pa.edited",
                        "softwareAgent": "Codex built-in GPT Image 2 + ArtFlow feathered-inside-mask-v2",
                        "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/compositeWithTrainedAlgorithmicMedia",
                        "parameters": {
                            "description": "Mask-bounded revision with pixel-exact outside-mask verification"
                        },
                    },
                    {
                        "action": "c2pa.placed",
                        "softwareAgent": "Unreal Engine 5.8 ArtFlow project-local return tool",
                        "parameters": {"ingredients": ["verified_revision"]},
                    },
                ]
            },
            "c2pa.ingredient.v3": [
                {
                    "dc:title": item.role,
                    "dc:format": item.media_type,
                    "relationship": "inputTo",
                    "data": {
                        "url": item.path,
                        "alg": "sha256",
                        "hash": item.sha256,
                    },
                }
                for item in ingredients
            ],
        },
        "unreal_return_receipt_sha256": receipt.receipt_sha256,
        "manifest_sha256": "0" * 64,
    }
    payload["manifest_sha256"] = canonical_sha256(payload, "manifest_sha256")
    manifest = ProvenanceManifest.model_validate(payload)
    manifest_path = OUTPUT_ROOT / "provenance-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"MANIFEST={manifest.manifest_sha256} INGREDIENTS={len(ingredients)}")


if __name__ == "__main__":
    main()
