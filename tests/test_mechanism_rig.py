import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from artflow_agent.mechanism_rig import MechanismRigRequest, file_sha256

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/goal/m51-s1-mechanism-rig"


def test_mechanism_rig_chain_is_content_bound_and_reconciled() -> None:
    request = MechanismRigRequest.model_validate_json(
        (EVIDENCE / "mechanism-rig-request.json").read_text(encoding="utf-8")
    )
    blender = json.loads(
        (EVIDENCE / "blender-mechanism-rig-receipt.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (EVIDENCE / "AF_ArticulatedGate-manifest.json").read_text(encoding="utf-8")
    )
    unreal = json.loads(
        (EVIDENCE / "unreal-mechanism-rig-receipt.json").read_text(encoding="utf-8")
    )

    assert blender["request_sha256"] == request.request_sha256
    assert blender["bone_count"] == 3
    assert blender["joint_count"] == 2
    assert blender["action_frame_range"] == [1, 48]
    assert blender["triangle_count"] <= request.triangle_budget
    for artifact in blender["artifacts"]:
        assert file_sha256(EVIDENCE / artifact["relative_path"]) == artifact["sha256"]
    assert [bone["bone_name"] for bone in manifest["bones"]] == [
        "root",
        "hinge_left",
        "hinge_right",
    ]
    assert unreal["blender_receipt_sha256"] == blender["receipt_sha256"]
    assert unreal["status"] == "reconciled"
    assert unreal["verified_deform_bones"] == ["root", "hinge_left", "hinge_right"]
    assert unreal["skeletal_mesh_path"].startswith("/Game/ArtFlow/Generated/Blender/Mechanism/")
    assert unreal["animation_path"].endswith(
        "SK_AF_ArticulatedGate_Anim.SK_AF_ArticulatedGate_Anim"
    )
    assert unreal["mechanism_actor_count"] == 1
    assert unreal["created_actor_count"] == 0
    assert unreal["duplicate_side_effect_count"] == 0
    assert unreal["source_candidate_sha256_before"] == unreal["source_candidate_sha256_after"]

    changed = request.model_dump(mode="json")
    changed["width_cm"] = 600
    with pytest.raises(ValidationError, match="fingerprint mismatch"):
        MechanismRigRequest.model_validate(changed)
