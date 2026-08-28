from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .provenance import canonical_sha256

MANIFEST_PATH = "release-manifest.json"
FIXED_ZIP_TIMESTAMP = (2026, 8, 25, 0, 0, 0)


class ReleaseFile(BaseModel):
    path: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,499}$")
    role: str = Field(pattern=r"^[a-z][a-z0-9._-]{2,79}$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    size: int = Field(ge=0)


class PortfolioReleaseManifest(BaseModel):
    schema_id: Literal["artflow-portfolio-release/1"] = "artflow-portfolio-release/1"
    release_id: str
    product: Literal["ArtFlow Agent"] = "ArtFlow Agent"
    run_id: str
    event_count: int = Field(ge=1)
    files: list[ReleaseFile] = Field(min_length=1)
    identities: dict[str, str]
    metrics: dict[str, str]
    limitations: list[str]
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    def expected_sha256(self) -> str:
        return canonical_sha256(self, "manifest_sha256")

    @model_validator(mode="after")
    def validate_manifest(self) -> PortfolioReleaseManifest:
        if self.manifest_sha256 != self.expected_sha256():
            raise ValueError("Portfolio release manifest hash mismatch")
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("Portfolio release paths must be unique")
        return self


class ReleaseVerification(BaseModel):
    schema_id: Literal["artflow-release-verification/1"] = (
        "artflow-release-verification/1"
    )
    status: Literal["passed", "failed"]
    verified_files: int = Field(ge=0)
    total_files: int = Field(ge=0)
    run_id: str | None = None
    event_count: int | None = None
    checks: list[str]
    failures: list[str]
    manifest_sha256: str | None = None


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def build_release_archive(
    *,
    output_root: Path,
    release_id: str,
    run_id: str,
    event_count: int,
    sources: list[tuple[Path, str, str]],
    generated_files: dict[str, bytes],
    identities: dict[str, str],
    metrics: dict[str, str],
    limitations: list[str],
) -> tuple[Path, PortfolioReleaseManifest]:
    content: dict[str, tuple[bytes, str]] = {}
    for source, archive_path, role in sources:
        if not source.is_file():
            raise FileNotFoundError(source)
        content[archive_path] = (source.read_bytes(), role)
    for archive_path, value in generated_files.items():
        content[archive_path] = (value, "release_document")
    if len(content) != len(sources) + len(generated_files):
        raise ValueError("Duplicate archive path in release source declaration")
    forbidden = ("prompt", "secret", ".env", ".sqlite", "agent-events")
    for archive_path in content:
        lowered = archive_path.lower()
        if any(token in lowered for token in forbidden):
            raise ValueError(f"Forbidden release path: {archive_path}")
        if archive_path.startswith("/") or ".." in Path(archive_path).parts:
            raise ValueError(f"Unsafe release path: {archive_path}")
    files = [
        ReleaseFile(
            path=path,
            role=content[path][1],
            sha256=sha256_bytes(content[path][0]),
            size=len(content[path][0]),
        )
        for path in sorted(content)
    ]
    manifest_payload = {
        "schema_id": "artflow-portfolio-release/1",
        "release_id": release_id,
        "product": "ArtFlow Agent",
        "run_id": run_id,
        "event_count": event_count,
        "files": [item.model_dump(mode="json") for item in files],
        "identities": identities,
        "metrics": metrics,
        "limitations": limitations,
        "manifest_sha256": "0" * 64,
    }
    manifest_payload["manifest_sha256"] = canonical_sha256(
        manifest_payload, "manifest_sha256"
    )
    manifest = PortfolioReleaseManifest.model_validate(manifest_payload)
    output_root.mkdir(parents=True, exist_ok=True)
    target = output_root / f"artflow-agent-portfolio-{manifest.manifest_sha256[:16]}.zip"
    temporary = target.with_suffix(".zip.part")
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(content):
            info = zipfile.ZipInfo(path, FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content[path][0])
        info = zipfile.ZipInfo(MANIFEST_PATH, FIXED_ZIP_TIMESTAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, canonical_json_bytes(manifest.model_dump(mode="json")))
    temporary.replace(target)
    return target, manifest


def verify_release_archive(path: Path) -> ReleaseVerification:
    failures: list[str] = []
    checks: list[str] = []
    verified = 0
    manifest: PortfolioReleaseManifest | None = None
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                failures.append("duplicate_zip_entries")
            if MANIFEST_PATH not in names:
                failures.append("missing_release_manifest")
                raise ValueError("manifest missing")
            manifest = PortfolioReleaseManifest.model_validate_json(
                archive.read(MANIFEST_PATH)
            )
            declared = {item.path: item for item in manifest.files}
            actual = set(names) - {MANIFEST_PATH}
            if actual != set(declared):
                failures.append("declared_file_set_mismatch")
            for name, entry in declared.items():
                if name not in actual:
                    continue
                value = archive.read(name)
                if len(value) != entry.size or sha256_bytes(value) != entry.sha256:
                    failures.append(f"file_hash_mismatch:{name}")
                else:
                    verified += 1
            _verify_embedded_evidence(archive, manifest, failures, checks)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        if not failures:
            failures.append(f"invalid_release:{type(exc).__name__}")
    return ReleaseVerification(
        status="failed" if failures else "passed",
        verified_files=verified,
        total_files=len(manifest.files) if manifest else 0,
        run_id=manifest.run_id if manifest else None,
        event_count=manifest.event_count if manifest else None,
        checks=checks,
        failures=failures,
        manifest_sha256=manifest.manifest_sha256 if manifest else None,
    )


def _verify_embedded_evidence(
    archive: zipfile.ZipFile,
    manifest: PortfolioReleaseManifest,
    failures: list[str],
    checks: list[str],
) -> None:
    summary = json.loads(archive.read("evidence/portfolio-summary.json"))
    harness = json.loads(archive.read("evidence/harness-scorecard.json"))
    recovery = json.loads(archive.read("evidence/recovery-scorecard.json"))
    memory = json.loads(archive.read("evidence/memory-scorecard.json"))
    delivery = json.loads(archive.read("evidence/verified-delivery.json"))
    provenance = json.loads(archive.read("evidence/provenance-verification.json"))
    if summary.get("run_id") != manifest.run_id:
        failures.append("summary_run_identity_mismatch")
    if summary.get("event_count") != manifest.event_count:
        failures.append("summary_event_count_mismatch")
    if harness.get("run_id") != manifest.run_id or (
        harness.get("passed_cases"), harness.get("total_cases")
    ) != (20, 20):
        failures.append("harness_identity_or_denominator_mismatch")
    if (recovery.get("passed_cases"), recovery.get("total_cases")) != (6, 6):
        failures.append("recovery_denominator_mismatch")
    if recovery.get("duplicate_side_effect_count") != 0:
        failures.append("recovery_duplicate_side_effect_mismatch")
    if (memory.get("passed_cases"), memory.get("total_cases")) != (6, 6):
        failures.append("memory_denominator_mismatch")
    if delivery.get("run_id") != manifest.run_id or (
        delivery.get("delivery_sha256")
        != manifest.identities.get("verified_delivery_sha256")
    ):
        failures.append("verified_delivery_identity_mismatch")
    if (
        provenance.get("status") != "passed_with_declared_limitations"
        or not provenance.get("hash_chain_valid")
        or (provenance.get("verified_bindings"), provenance.get("total_bindings"))
        != (9, 9)
        or provenance.get("c2pa_signature_status") != "not_present"
    ):
        failures.append("provenance_boundary_mismatch")
    checks.extend(
        [
            "all_packaged_files_content_addressed",
            "run_and_event_identity_bound",
            "harness_20_of_20",
            "recovery_6_of_6_zero_duplicates",
            "memory_6_of_6",
            "provenance_9_of_9_unsigned_boundary",
        ]
    )
    if summary.get("schema_id") == "artflow-portfolio-summary/2":
        _verify_extended_evidence(archive, failures, checks)


def _verify_extended_evidence(
    archive: zipfile.ZipFile,
    failures: list[str],
    checks: list[str],
) -> None:
    pbr = json.loads(archive.read("evidence/m8-pbr-verification.json"))
    multi_domain = json.loads(archive.read("evidence/m9-multi-domain-verification.json"))
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
        or set(multi_domain.get("operation_statuses", {}).values()) != {"reconciled"}
    ):
        failures.append("multi_domain_verification_mismatch")
    if (
        correction.get("status") != "verified"
        or correction.get("rerun_domains") != ["lighting"]
        or correction.get("correction_reconcile_external_submissions") != 0
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
