from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from pydantic import BaseModel, Field

from .contracts import SceneConstraintPackage
from .contracts.scene import ArtifactRef

MAX_ARCHIVE_FILES = 256
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 200


class ScenePackageImportError(ValueError):
    """Raised when an atomic scene package fails closed before entering orchestration."""


class VerifiedSceneArtifact(BaseModel):
    path: str
    sha256: str
    size_bytes: int = Field(ge=0)


class ScenePackagePreview(BaseModel):
    package: SceneConstraintPackage
    archive_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifacts: list[VerifiedSceneArtifact]

    @property
    def protected_region_ids(self) -> list[str]:
        return [item.region_id for item in self.package.regions if item.mode == "protected"]

    @property
    def editable_region_ids(self) -> list[str]:
        return [item.region_id for item in self.package.regions if item.mode == "editable"]


class ScenePackageArchive:
    """Read-only adapter for an atomic archive captured by a future Unreal Bridge."""

    manifest_name = "scene-package.json"

    def inspect(self, archive_path: Path) -> ScenePackagePreview:
        if not archive_path.is_file():
            raise ScenePackageImportError(f"Scene package archive not found: {archive_path}")
        archive_sha256 = _sha256_file(archive_path)
        try:
            with ZipFile(archive_path) as archive:
                entries = _validate_archive_entries(archive.infolist())
                manifest_info = entries.get(self.manifest_name)
                if manifest_info is None:
                    raise ScenePackageImportError(
                        f"Scene package is missing {self.manifest_name}"
                    )
                try:
                    payload = json.loads(archive.read(manifest_info))
                    package = SceneConstraintPackage.model_validate(payload)
                except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
                    raise ScenePackageImportError(f"Invalid scene package manifest: {exc}") from exc

                verified: list[VerifiedSceneArtifact] = []
                for artifact in _artifact_refs(package):
                    info = entries.get(artifact.path)
                    if info is None or info.is_dir():
                        raise ScenePackageImportError(
                            f"Referenced scene artifact is missing: {artifact.path}"
                        )
                    digest = _sha256_stream(archive.open(info))
                    if digest != artifact.sha256:
                        raise ScenePackageImportError(
                            f"Scene artifact hash mismatch: {artifact.path}"
                        )
                    verified.append(
                        VerifiedSceneArtifact(
                            path=artifact.path,
                            sha256=digest,
                            size_bytes=info.file_size,
                        )
                    )
        except BadZipFile as exc:
            raise ScenePackageImportError("Scene package is not a valid ZIP archive") from exc

        return ScenePackagePreview(
            package=package,
            archive_sha256=archive_sha256,
            artifacts=verified,
        )


def _artifact_refs(package: SceneConstraintPackage) -> list[ArtifactRef]:
    artifacts = [
        *(item.artifact for item in package.passes),
        *package.art_intent.reference_assets,
    ]
    for artifact in (
        package.scene_digital_twin,
        package.scene_change_plan,
        package.scene_dry_run_receipt,
    ):
        if artifact is not None:
            artifacts.append(artifact)
    return artifacts


def _validate_archive_entries(entries: list[ZipInfo]) -> dict[str, ZipInfo]:
    if len(entries) > MAX_ARCHIVE_FILES:
        raise ScenePackageImportError("Scene package contains too many files")
    total_size = sum(item.file_size for item in entries)
    if total_size > MAX_UNCOMPRESSED_BYTES:
        raise ScenePackageImportError("Scene package is too large after decompression")

    by_name: dict[str, ZipInfo] = {}
    for info in entries:
        normalized = info.filename.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not normalized
            or path.is_absolute()
            or ".." in path.parts
            or normalized != path.as_posix()
        ):
            raise ScenePackageImportError(f"Unsafe archive entry: {info.filename}")
        if normalized in by_name:
            raise ScenePackageImportError(f"Duplicate archive entry: {normalized}")
        if info.flag_bits & 0x1:
            raise ScenePackageImportError(f"Encrypted archive entry is unsupported: {normalized}")
        if info.file_size and info.compress_size == 0:
            raise ScenePackageImportError(f"Invalid compressed size: {normalized}")
        if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
            raise ScenePackageImportError(f"Suspicious compression ratio: {normalized}")
        by_name[normalized] = info
    return by_name


def _sha256_stream(stream: object) -> str:
    digest = hashlib.sha256()
    while chunk := stream.read(1024 * 1024):  # type: ignore[attr-defined]
        digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return _sha256_stream(stream)
