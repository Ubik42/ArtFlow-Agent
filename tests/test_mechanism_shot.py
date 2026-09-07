from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.mechanism_shot import (
    MechanismShotRequest,
    compile_mechanism_shot_request,
)
from artflow_agent.scene_lifecycle import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/goal/m53-s1-mechanism-shot"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_request_is_bound_to_the_registered_mechanism() -> None:
    request = compile_mechanism_shot_request(root=ROOT)
    frozen = MechanismShotRequest.model_validate_json(
        (EVIDENCE / "mechanism-shot-request.json").read_text(encoding="utf-8")
    )

    assert request == frozen
    assert request.capability_id == "unreal.sequencer.mechanism_shot.v1"
    assert request.camera_binding_mode == "spawnable"
    assert request.camera_cut_binding_space == "sequence_local"
    assert request.camera_transform_track == "constant"
    assert [(item.label, item.frame) for item in request.frames] == [
        ("closed_start", 1),
        ("open", 24),
        ("closed_end", 48),
    ]


def test_reconciled_unreal_receipt_binds_three_sequence_frames() -> None:
    request = json.loads(
        (EVIDENCE / "mechanism-shot-request.json").read_text(encoding="utf-8")
    )
    receipt = json.loads(
        (EVIDENCE / "unreal-mechanism-shot-receipt.json").read_text(encoding="utf-8")
    )
    unsigned = dict(receipt)
    receipt_sha = unsigned.pop("receipt_sha256")

    assert canonical_sha256(unsigned) == receipt_sha
    assert receipt["request_sha256"] == request["request_sha256"]
    assert receipt["status"] == "reconciled"
    assert receipt["source_candidate_sha256_before"] == receipt["source_candidate_sha256_after"]
    assert receipt["mechanism_binding_count"] == 1
    assert receipt["animation_track_count"] == 1
    assert receipt["animation_section_count"] == 1
    assert receipt["camera_binding_count"] == 1
    assert receipt["light_binding_count"] == 1
    assert receipt["camera_cut_track_count"] == 1
    assert receipt["created_actor_count"] == 0
    assert receipt["created_package_count"] == 0
    assert receipt["created_binding_count"] == 0
    assert receipt["created_track_count"] == 0
    assert receipt["duplicate_track_count"] == 0
    assert receipt["frame_numbers"] == [1, 24, 48]
    assert receipt["preview_capture_mode"] == "sequencer_render_movie"
    for label, relative_path in receipt["preview_paths"].items():
        assert sha256(EVIDENCE / relative_path) == receipt["preview_sha256s"][label]
    assert len(set(receipt["preview_sha256s"].values())) == 3


def test_request_rejects_a_changed_shot_recipe() -> None:
    payload = json.loads(
        (EVIDENCE / "mechanism-shot-request.json").read_text(encoding="utf-8")
    )
    payload["frames"][1]["frame"] = 20
    with pytest.raises(ValidationError):
        MechanismShotRequest.model_validate(payload)
