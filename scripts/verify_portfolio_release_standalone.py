"""Standard-library verifier shipped inside the ArtFlow portfolio release."""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_hash(value: dict, field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return sha256(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


def verify(path: Path) -> dict:
    failures: list[str] = []
    checks: list[str] = []
    verified = 0
    manifest = None
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                failures.append("duplicate_zip_entries")
            manifest = json.loads(archive.read("release-manifest.json"))
            if manifest.get("schema_id") != "artflow-portfolio-release/1":
                failures.append("unsupported_manifest_schema")
            if canonical_hash(manifest, "manifest_sha256") != manifest.get(
                "manifest_sha256"
            ):
                failures.append("manifest_hash_mismatch")
            declared = {item["path"]: item for item in manifest["files"]}
            if set(names) - {"release-manifest.json"} != set(declared):
                failures.append("declared_file_set_mismatch")
            for name, entry in declared.items():
                if name not in names:
                    continue
                content = archive.read(name)
                if len(content) != entry["size"] or sha256(content) != entry["sha256"]:
                    failures.append(f"file_hash_mismatch:{name}")
                else:
                    verified += 1
            summary = json.loads(archive.read("evidence/portfolio-summary.json"))
            harness = json.loads(archive.read("evidence/harness-scorecard.json"))
            recovery = json.loads(archive.read("evidence/recovery-scorecard.json"))
            memory = json.loads(archive.read("evidence/memory-scorecard.json"))
            delivery = json.loads(archive.read("evidence/verified-delivery.json"))
            provenance = json.loads(
                archive.read("evidence/provenance-verification.json")
            )
            if summary.get("run_id") != manifest.get("run_id") or summary.get(
                "event_count"
            ) != manifest.get("event_count"):
                failures.append("run_identity_mismatch")
            if harness.get("run_id") != manifest.get("run_id") or (
                harness.get("passed_cases"), harness.get("total_cases")
            ) != (20, 20):
                failures.append("harness_denominator_mismatch")
            if (
                recovery.get("passed_cases"),
                recovery.get("total_cases"),
                recovery.get("duplicate_side_effect_count"),
            ) != (6, 6, 0):
                failures.append("recovery_denominator_mismatch")
            if (memory.get("passed_cases"), memory.get("total_cases")) != (6, 6):
                failures.append("memory_denominator_mismatch")
            if delivery.get("run_id") != manifest.get("run_id") or delivery.get(
                "delivery_sha256"
            ) != manifest.get("identities", {}).get("verified_delivery_sha256"):
                failures.append("delivery_identity_mismatch")
            if (
                provenance.get("verified_bindings"),
                provenance.get("total_bindings"),
                provenance.get("c2pa_signature_status"),
            ) != (9, 9, "not_present") or not provenance.get("hash_chain_valid"):
                failures.append("provenance_boundary_mismatch")
            checks.extend(
                [
                    "all_packaged_files_content_addressed",
                    "run_event_head_bound",
                    "harness_20_of_20",
                    "recovery_6_of_6_zero_duplicates",
                    "memory_6_of_6",
                    "provenance_9_of_9_unsigned_boundary",
                ]
            )
            if summary.get("schema_id") == "artflow-portfolio-summary/2":
                pbr = json.loads(archive.read("evidence/m8-pbr-verification.json"))
                multi_domain = json.loads(
                    archive.read("evidence/m9-multi-domain-verification.json")
                )
                correction = json.loads(
                    archive.read("evidence/m9-correction-publish-verification.json")
                )
                mcp = json.loads(archive.read("evidence/m10-mcp-boundary-audit.json"))
                image_to_3d = json.loads(
                    archive.read("evidence/m10-image-to-3d-verification.json")
                )
                if (
                    pbr.get("status") != "verified"
                    or len(pbr.get("texture_hashes", {})) != 5
                    or pbr.get("invalid_attempts_rejected") != 2
                    or not pbr.get("source_scene_unchanged")
                ):
                    failures.append("pbr_verification_mismatch")
                if (
                    multi_domain.get("status") != "verified"
                    or multi_domain.get("generated_instance_count") != 12
                    or multi_domain.get("instances_inside_exclusion") != 0
                    or set(multi_domain.get("operation_statuses", {}).values())
                    != {"reconciled"}
                ):
                    failures.append("multi_domain_verification_mismatch")
                if (
                    correction.get("status") != "verified"
                    or correction.get("rerun_domains") != ["lighting"]
                    or correction.get("correction_reconcile_external_submissions")
                    != 0
                    or correction.get("publish_replay_duplicate_side_effects") != 0
                ):
                    failures.append("correction_verification_mismatch")
                if (
                    mcp.get("status") != "verified"
                    or (mcp.get("resource_count"), mcp.get("tool_count")) != (3, 4)
                    or mcp.get("hostile_rejection_count") != 4
                    or mcp.get("arbitrary_execution_surface_count") != 0
                ):
                    failures.append("mcp_boundary_mismatch")
                if (
                    image_to_3d.get("status") != "verified"
                    or image_to_3d.get("unreal_triangles") != 4_817
                    or image_to_3d.get("unreal_material_slots") != 1
                    or image_to_3d.get("unreal_simple_collisions") != 1
                    or not image_to_3d.get("hostile_triangle_budget_rejected")
                    or not image_to_3d.get("source_scene_unchanged")
                ):
                    failures.append("image_to_3d_verification_mismatch")
                checks.extend(
                    [
                        "pbr_5_channels_2_invalid_attempts_rejected",
                        "multi_domain_4_reconciled_12_instances_zero_incursions",
                        "lighting_only_correction_zero_resubmission",
                        "mcp_3_resources_4_tools_4_hostile_rejections",
                        "image_to_3d_interchange_and_budget_negative_control",
                    ]
                )
    except (OSError, KeyError, ValueError, zipfile.BadZipFile) as exc:
        if not failures:
            failures.append(f"invalid_release:{type(exc).__name__}")
    return {
        "schema_id": "artflow-release-verification/1",
        "status": "failed" if failures else "passed",
        "verified_files": verified,
        "total_files": len(manifest["files"]) if manifest else 0,
        "run_id": manifest.get("run_id") if manifest else None,
        "event_count": manifest.get("event_count") if manifest else None,
        "checks": checks,
        "failures": failures,
        "manifest_sha256": manifest.get("manifest_sha256") if manifest else None,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python verify_release.py <artflow-release.zip>")
    result = verify(Path(sys.argv[1]).resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)
