from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from artflow_agent.pbr import ComfyCapabilitySnapshot, canonical_sha256
from artflow_agent.pbr_unreal import UnrealPBRReturnRequest
from artflow_agent.pbr_validation import PBRGenerationValidationReceipt
from artflow_agent.scene_session import (
    SceneCandidateMaterialToolCall,
    SceneCandidatePCGToolCall,
    SceneCandidatePlan,
    SceneCandidateProjectAssetToolCall,
)


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seal the M13 cross-pipeline candidate plan.")
    parser.add_argument("--handshake", type=Path, required=True)
    parser.add_argument("--capability", type=Path, required=True)
    parser.add_argument("--validation-receipt", type=Path, required=True)
    parser.add_argument("--unreal-request", type=Path, required=True)
    parser.add_argument("--project-asset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--host-receipt", type=Path, required=True)
    args = parser.parse_args()

    host = json.loads(args.handshake.read_text(encoding="utf-8"))
    receipt = host["artflow_receipt"]
    base = SceneCandidatePlan.model_validate(receipt["candidate_plan"])
    capability = ComfyCapabilitySnapshot.model_validate_json(
        args.capability.read_text(encoding="utf-8")
    )
    validation = PBRGenerationValidationReceipt.model_validate_json(
        args.validation_receipt.read_text(encoding="utf-8")
    )
    unreal_request = UnrealPBRReturnRequest.model_validate_json(
        args.unreal_request.read_text(encoding="utf-8")
    )
    if validation.status != "validated":
        raise SystemExit("cross-pipeline plan requires a validated five-channel PBR set")
    if validation.capability_snapshot_sha256 != capability.snapshot_sha256:
        raise SystemExit("PBR receipt does not cite the current ComfyUI capability snapshot")
    pcg = next(item for item in base.operations if isinstance(item, SceneCandidatePCGToolCall))
    material = SceneCandidateMaterialToolCall(
        operation_id="material-rain-wet-main",
        target_actor_id=pcg.target_actor_id,
        target_actor_label=pcg.target_actor_label,
        expected_source_fingerprint=pcg.expected_source_fingerprint,
        capability_snapshot_sha256=capability.snapshot_sha256,
        generation_receipt_sha256=file_sha256(args.validation_receipt),
        unreal_import_request_sha256=unreal_request.request_sha256,
        material_instance_path=(
            f"{unreal_request.destination_root}/{unreal_request.material_instance_name}."
            f"{unreal_request.material_instance_name}"
        ),
    )
    asset = SceneCandidateProjectAssetToolCall(
        operation_id="project-assets-courtyard-rocks",
        asset_set_id="courtyard-rocks-v1",
        approved_asset_paths=["/Game/ArtFlow/Props/SM_ArtFlowRock.SM_ArtFlowRock"],
        approved_asset_sha256s=[file_sha256(args.project_asset)],
    )
    operations = [material, asset, *base.operations]
    payload = base.model_dump(
        mode="json",
        exclude={"schema_id", "plan_id", "plan_sha256", "operations"},
    )
    payload["operations"] = [item.model_dump(mode="json") for item in operations]
    digest = canonical_sha256(payload)
    plan = SceneCandidatePlan(
        plan_id=f"candidate-plan-{digest[:12]}",
        plan_sha256=digest,
        **payload,
    )
    args.output.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")

    receipt["candidate_plan"] = plan.model_dump(mode="json")
    handshake_payload = {
        key: value
        for key, value in receipt.items()
        if key not in {"schema_id", "handshake_id", "handshake_sha256"}
    }
    handshake_digest = canonical_sha256(handshake_payload)
    receipt["handshake_id"] = f"scene-handshake-{handshake_digest[:12]}"
    receipt["handshake_sha256"] = handshake_digest
    args.host_receipt.write_text(json.dumps(host, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(plan.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
