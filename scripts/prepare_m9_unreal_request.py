from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path

from artflow_agent.contracts import MultiDomainSceneDeltaPlan, SceneDigitalTwin
from artflow_agent.multi_domain_unreal import MultiDomainUnrealRequest, canonical_sha256
from artflow_agent.scene_orchestration import MultiDomainDryRunReceipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Bind the M9 v2 plan to real UE scene facts.")
    parser.add_argument("--scene-package", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--dry-run", type=Path, required=True)
    parser.add_argument("--pbr-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with zipfile.ZipFile(args.scene_package) as archive:
        twin_bytes = archive.read("scene-digital-twin.json")
        twin = SceneDigitalTwin.model_validate_json(twin_bytes)
    twin_file_sha256 = hashlib.sha256(twin_bytes).hexdigest()
    plan = MultiDomainSceneDeltaPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    dry_run = MultiDomainDryRunReceipt.model_validate_json(args.dry_run.read_text(encoding="utf-8"))
    pbr = json.loads(args.pbr_receipt.read_text(encoding="utf-8"))
    if plan.canonical_sha256() != dry_run.plan_sha256:
        raise SystemExit("dry-run receipt is not bound to the M9 plan")
    if plan.twin_id != twin.twin_id or plan.twin_sha256 != twin_file_sha256:
        raise SystemExit("M9 plan is not bound to the real Scene Digital Twin")
    by_label = {actor.label: actor for actor in twin.actors}
    required_labels = {
        "editable": "Editable_Form",
        "protected": "Protected_Blockout",
        "key_light": "ArtFlow_KeyLight",
        "authored_camera": "ArtFlow_Camera",
    }
    if any(label not in by_label for label in required_labels.values()):
        raise SystemExit("Scene Digital Twin is missing an M9 actor binding")
    editable = by_label["Editable_Form"]
    protected = by_label["Protected_Blockout"]
    pcg_fact = next(
        (component for component in editable.pcg_components if component.component_id.endswith(":pcg_artflowscatter")),
        None,
    )
    if pcg_fact is None:
        raise SystemExit("real editable actor has no reviewed ArtFlow PCG component")
    operations = {item.operation_id: item for item in plan.operations}
    material = operations["material-bind"]
    asset = operations["asset-reuse"]
    lighting = operations["lighting-patch"]
    pcg = operations["pcg-layout"]
    unsigned = {
        "schema_id": "multi-domain-unreal-request/1",
        "request_id": "m9-ue-000000000000000000000000",
        "plan_id": plan.plan_id,
        "plan_sha256": plan.canonical_sha256(),
        "dry_run_receipt_sha256": dry_run.receipt_sha256,
        "twin_id": twin.twin_id,
        "twin_sha256": twin_file_sha256,
        "source_scene_path": twin.scene_path,
        "source_scene_sha256": pbr["source_scene_sha256_before"],
        "candidate_scene_path": pbr["destination_scene_path"],
        "stage_id": dry_run.stage_id,
        "actors": [
            {
                "role": role,
                "actor_id": by_label[label].actor_id,
                "label": label,
                "source_fingerprint": by_label[label].source_fingerprint,
            }
            for role, label in required_labels.items()
        ],
        "operation_order": dry_run.unreal_apply_order,
        "material": {
            "target_role": "editable",
            "slot_index": material.slot_index,
            "material_instance_path": pbr["material_instance_path"],
            "pbr_request_sha256": pbr["request_sha256"],
            "pbr_receipt_sha256": pbr["receipt_sha256"],
        },
        "asset": {
            "asset_paths": asset.asset_paths,
            "license_policy": asset.license_policy,
        },
        "lighting": {
            "target_role": "key_light",
            "intensity": lighting.intensity,
            "temperature_kelvin": lighting.temperature_kelvin,
        },
        "pcg": {
            "target_role": "editable",
            "component_id": pcg_fact.component_id,
            "reviewed_graph_path": pcg_fact.graph_path,
            "reviewed_graph_sha256": pcg_fact.graph_fingerprint,
            "seed": pcg.seed,
            "expected_instance_count": asset.spawn_count,
            "exclusion_bounds": protected.bounds.model_dump(mode="json"),
        },
        "render": {
            "authored_camera_role": "authored_camera",
            "validation_camera_location": [-620.0, -650.0, 330.0],
            "validation_camera_target": [0.0, 40.0, 105.0],
            "width": 640,
            "height": 360,
        },
        "expected_protected_state_sha256": pbr["protected_state_before"],
    }
    identity = canonical_sha256(unsigned)[:24]
    unsigned["request_id"] = f"m9-ue-{identity}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    request = MultiDomainUnrealRequest.model_validate(unsigned)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(request.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
