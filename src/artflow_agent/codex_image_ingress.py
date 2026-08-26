from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import uuid
from pathlib import Path

from .agent_runtime import AgentEventStore, AgentRuntimeError
from .contracts import (
    CodexImageCandidateReceipt,
    CodexImageCandidateRecord,
    CodexImageRequestBinding,
    ReceiptArtifact,
)
from .contracts.codex_image import imported_at_now
from .negative_control import (
    NegativeControlReceipt,
    NegativeControlRecord,
    NegativeControlRequest,
)


def import_codex_image_candidate(
    store: AgentEventStore,
    run_id: str,
    image_path: Path,
    prompt_text: str,
    *,
    artifact_root: Path,
    expected_archive_sha256: str,
    expected_beauty_sha256: str,
) -> CodexImageCandidateRecord:
    """Normalize one already-returned built-in image without invoking a provider API."""

    state = store.load(run_id)
    if state.scene is None:
        raise AgentRuntimeError("Codex image import requires an attached Scene Package")
    beauty = next(
        (item for item in state.scene.package.passes if item.kind == "beauty"),
        None,
    )
    if beauty is None:
        raise AgentRuntimeError("Attached Scene Package has no beauty pass")
    if (
        expected_archive_sha256 != state.scene.archive_sha256
        or expected_beauty_sha256 != beauty.artifact.sha256
    ):
        raise AgentRuntimeError("Expected Codex source binding does not match the run")

    source_sha256 = _sha256_file(image_path)
    width, height = _inspect_png(image_path)
    candidate_id = f"codex-{source_sha256[:20]}"
    request = CodexImageRequestBinding(
        scene_package_id=state.scene.package.package_id,
        scene_package_sha256=state.scene.archive_sha256,
        beauty_sha256=beauty.artifact.sha256,
        art_goal=state.scene.package.art_intent.goal,
        preserve=state.scene.package.art_intent.preserve,
        prohibit=state.scene.package.art_intent.prohibit,
        prompt_sha256=hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
    )

    existing = next(
        (
            item
            for item in state.codex_image_candidates
            if item.receipt.candidate_id == candidate_id
        ),
        None,
    )
    if existing is not None:
        if (
            existing.request != request
            or existing.receipt.artifact.sha256 != source_sha256
            or existing.receipt.width != width
            or existing.receipt.height != height
        ):
            raise AgentRuntimeError("Persisted Codex candidate conflicts with import evidence")
        _verify_persisted_artifact(artifact_root, existing.receipt.artifact.sha256)
        return existing

    artifact_root.mkdir(parents=True, exist_ok=True)
    persisted_path = artifact_root / f"{source_sha256}.png"
    if persisted_path.exists():
        _verify_persisted_artifact(artifact_root, source_sha256)
    else:
        temporary = artifact_root / f".{uuid.uuid4().hex}.importing"
        try:
            shutil.copyfile(image_path, temporary)
            if _sha256_file(temporary) != source_sha256:
                raise AgentRuntimeError("Copied Codex candidate failed content verification")
            os.replace(temporary, persisted_path)
        finally:
            temporary.unlink(missing_ok=True)

    receipt = CodexImageCandidateReceipt(
        candidate_id=candidate_id,
        request_binding_sha256=request.fingerprint(),
        artifact=ReceiptArtifact(
            path=f"provider-outputs/{source_sha256}.png",
            sha256=source_sha256,
            media_type="image/png",
        ),
        width=width,
        height=height,
        imported_at=imported_at_now(),
    )
    record = CodexImageCandidateRecord(request=request, receipt=receipt)
    store.record_codex_image_candidate(run_id, record)

    receipt_root = artifact_root.parent / "codex-receipts"
    receipt_root.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_root / f"{candidate_id}.json"
    payload = json.dumps(record.model_dump(mode="json"), indent=2) + "\n"
    temporary_receipt = receipt_path.with_suffix(".json.tmp")
    temporary_receipt.write_text(payload, encoding="utf-8")
    os.replace(temporary_receipt, receipt_path)
    return record


def import_negative_control(
    store: AgentEventStore,
    run_id: str,
    image_path: Path,
    prompt_text: str,
    *,
    artifact_root: Path,
    expected_archive_sha256: str,
    expected_beauty_sha256: str,
) -> NegativeControlRecord:
    state = store.load(run_id)
    if state.scene is None:
        raise AgentRuntimeError("Negative-control import requires an attached Scene Package")
    beauty = next(
        (item for item in state.scene.package.passes if item.kind == "beauty"),
        None,
    )
    if beauty is None or (
        expected_archive_sha256 != state.scene.archive_sha256
        or expected_beauty_sha256 != beauty.artifact.sha256
    ):
        raise AgentRuntimeError("Expected negative-control source binding does not match")
    source_sha256 = _sha256_file(image_path)
    width, height = _inspect_png(image_path)
    control_id = f"negative-{source_sha256[:20]}"
    request = NegativeControlRequest(
        scene_package_id=state.scene.package.package_id,
        scene_package_sha256=state.scene.archive_sha256,
        beauty_sha256=beauty.artifact.sha256,
        prompt_sha256=hashlib.sha256(prompt_text.encode("utf-8")).hexdigest(),
        intended_violations=[
            "protected_geometry_redesign",
            "sphere_relocation",
            "camera_framing_change",
            "ground_plane_composition_change",
        ],
    )
    existing = next(
        (
            item
            for item in state.negative_controls
            if item.receipt.control_id == control_id
        ),
        None,
    )
    if existing is not None:
        if existing.request != request or existing.receipt.artifact.sha256 != source_sha256:
            raise AgentRuntimeError("Persisted negative control conflicts with import evidence")
        _verify_persisted_artifact(artifact_root, source_sha256)
        return existing
    artifact_root.mkdir(parents=True, exist_ok=True)
    persisted_path = artifact_root / f"{source_sha256}.png"
    if persisted_path.exists():
        _verify_persisted_artifact(artifact_root, source_sha256)
    else:
        temporary = artifact_root / f".{uuid.uuid4().hex}.importing"
        try:
            shutil.copyfile(image_path, temporary)
            if _sha256_file(temporary) != source_sha256:
                raise AgentRuntimeError("Copied negative control failed verification")
            os.replace(temporary, persisted_path)
        finally:
            temporary.unlink(missing_ok=True)
    receipt = NegativeControlReceipt(
        control_id=control_id,
        request_binding_sha256=request.fingerprint(),
        artifact=ReceiptArtifact(
            path=f"provider-outputs/{source_sha256}.png",
            sha256=source_sha256,
            media_type="image/png",
        ),
        width=width,
        height=height,
        imported_at=imported_at_now(),
    )
    record = NegativeControlRecord(request=request, receipt=receipt)
    store.record_negative_control(run_id, record)
    receipt_root = artifact_root.parent / "negative-control-receipts"
    receipt_root.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_root / f"{control_id}.json"
    temporary_receipt = receipt_path.with_suffix(".json.tmp")
    temporary_receipt.write_text(
        json.dumps(record.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_receipt, receipt_path)
    return record


def _verify_persisted_artifact(artifact_root: Path, expected_sha256: str) -> Path:
    path = artifact_root / f"{expected_sha256}.png"
    if not path.is_file():
        raise AgentRuntimeError("Codex candidate artifact is not persisted")
    if _sha256_file(path) != expected_sha256:
        raise AgentRuntimeError("Persisted Codex candidate hash does not match receipt")
    _inspect_png(path)
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AgentRuntimeError(f"Codex candidate cannot be read: {exc}") from exc
    return digest.hexdigest()


def _inspect_png(path: Path) -> tuple[int, int]:
    try:
        header = path.read_bytes()[:24]
    except OSError as exc:
        raise AgentRuntimeError(f"Codex candidate cannot be read: {exc}") from exc
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise AgentRuntimeError("Codex candidate is not a valid PNG header")
    width, height = struct.unpack(">II", header[16:24])
    if width < 64 or height < 64:
        raise AgentRuntimeError("Codex candidate dimensions are invalid")
    return width, height
