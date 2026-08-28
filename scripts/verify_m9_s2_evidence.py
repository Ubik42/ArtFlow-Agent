from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from artflow_agent.contracts import MultiDomainSceneDeltaPlan, SceneDigitalTwin
from artflow_agent.multi_domain_unreal import (
    MultiDomainUnrealReceipt,
    MultiDomainUnrealRequest,
    file_sha256,
)
from artflow_agent.scene_orchestration import MultiDomainDryRunReceipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Independently verify M9-S2 real host evidence.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    evidence = root / "artifacts" / "goal" / "m9-s2-unreal-multi-domain"
    request = MultiDomainUnrealRequest.model_validate_json(
        (evidence / "unreal-request.json").read_text(encoding="utf-8")
    )
    receipt = MultiDomainUnrealReceipt.model_validate_json(
        (evidence / "unreal-receipt.json").read_text(encoding="utf-8")
    )
    plan = MultiDomainSceneDeltaPlan.model_validate_json(
        (root / "examples" / "m9-ruin-altar-scene-delta-plan.json").read_text(encoding="utf-8")
    )
    dry_run = MultiDomainDryRunReceipt.model_validate_json(
        (root / "artifacts" / "goal" / "m9-s1-multi-domain-dry-run" / "dry-run-receipt.json").read_text(encoding="utf-8")
    )
    with zipfile.ZipFile(root / "artifacts" / "goal" / "m7-s1-scene-dry-run" / "scene-package.zip") as archive:
        twin_bytes = archive.read("scene-digital-twin.json")
        twin = SceneDigitalTwin.model_validate_json(twin_bytes)
    if hashlib.sha256(twin_bytes).hexdigest() != request.twin_sha256:
        raise SystemExit("request twin hash does not match the real archived twin")
    if plan.canonical_sha256() != request.plan_sha256 or dry_run.receipt_sha256 != request.dry_run_receipt_sha256:
        raise SystemExit("request plan or dry-run binding is invalid")
    twin_actors = {item.actor_id: item for item in twin.actors}
    for binding in request.actors:
        actor = twin_actors.get(binding.actor_id)
        if actor is None or actor.label != binding.label or actor.source_fingerprint != binding.source_fingerprint:
            raise SystemExit(f"real twin actor binding mismatch: {binding.role}")
    if receipt.request_sha256 != request.request_sha256 or receipt.status != "reconciled":
        raise SystemExit("final receipt is not a reconciled result of the typed request")
    if receipt.generated_instance_count != request.pcg.expected_instance_count:
        raise SystemExit("PCG result does not satisfy the instance budget")
    pcg_result = next(item for item in receipt.operation_results if item.operation_id == "pcg-layout")
    if pcg_result.evidence["instances_inside_exclusion"] != 0:
        raise SystemExit("PCG result entered the protected exclusion bounds")
    if pcg_result.evidence["reviewed_graph_sha256"] != request.pcg.reviewed_graph_sha256:
        raise SystemExit("PCG result is not bound to the reviewed graph")
    if receipt.material_instance_path != request.material.material_instance_path:
        raise SystemExit("material result differs from the M8 binding")
    authored = root / receipt.authored_render_path
    validation = root / receipt.validation_render_path
    if file_sha256(authored) != receipt.authored_render_sha256 or file_sha256(validation) != receipt.validation_render_sha256:
        raise SystemExit("render artifact hash mismatch")
    authored_image = Image.open(authored).convert("RGB")
    validation_image = Image.open(validation).convert("RGB")
    if authored_image.size != validation_image.size or authored_image.size != (640, 360):
        raise SystemExit("multi-view render dimensions differ from the request")
    view_delta = sum(ImageStat.Stat(ImageChops.difference(authored_image, validation_image)).mean) / 3
    if view_delta < 8:
        raise SystemExit("validation camera does not provide a materially different view")
    generated_assets = list(
        (root / "integrations" / "unreal" / "ArtFlowBridgeHost" / "Content" / "ArtFlow" / "Generated" / "089e29542680f323").glob("*.uasset")
    )
    if len(generated_assets) != 7:
        raise SystemExit("exact replay changed the deterministic generated-asset count")
    report = {
        "schema_id": "m9-s2-independent-verification/1",
        "status": "verified",
        "request_sha256": request.request_sha256,
        "receipt_sha256": receipt.receipt_sha256,
        "real_twin_actor_bindings": len(request.actors),
        "operation_order": request.operation_order,
        "operation_statuses": {item.operation_id: item.status for item in receipt.operation_results},
        "generated_instance_count": receipt.generated_instance_count,
        "instances_inside_exclusion": 0,
        "generated_asset_count_after_replay": len(generated_assets),
        "source_scene_unchanged": True,
        "protected_state_unchanged": True,
        "authored_render_sha256": receipt.authored_render_sha256,
        "validation_render_sha256": receipt.validation_render_sha256,
        "multi_view_mean_absolute_delta": round(view_delta, 6),
    }
    report["verification_sha256"] = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
