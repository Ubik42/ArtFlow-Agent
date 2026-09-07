import json
import struct
from pathlib import Path

from artflow_agent.damage_variant import (
    DamageFieldReceipt,
    DamageVariantRequest,
    file_sha256,
)
from artflow_agent.scene_lifecycle import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/goal/m55-s1-damage-variant"
request = DamageVariantRequest.model_validate_json(
    (EVIDENCE / "damage-variant-request.json").read_text(encoding="utf-8")
)
comfy = DamageFieldReceipt.model_validate_json(
    (EVIDENCE / "comfy-damage-field-receipt.json").read_text(encoding="utf-8")
)
blender = json.loads(
    (EVIDENCE / "blender-damage-variant-receipt.json").read_text(encoding="utf-8")
)
unreal = json.loads(
    (EVIDENCE / "unreal-damage-variant-receipt.json").read_text(encoding="utf-8")
)
for receipt in (blender, unreal):
    unsigned = dict(receipt)
    receipt_sha256 = unsigned.pop("receipt_sha256")
    if canonical_sha256(unsigned) != receipt_sha256:
        raise RuntimeError(f"receipt identity changed: {receipt['schema_id']}")
if comfy.request_sha256 != request.request_sha256:
    raise RuntimeError("Comfy receipt references another request")
if blender["comfy_receipt_sha256"] != comfy.receipt_sha256:
    raise RuntimeError("Blender receipt references another Comfy result")
if unreal["blender_receipt_sha256"] != blender["receipt_sha256"]:
    raise RuntimeError("Unreal receipt references another Blender result")
for item in blender["artifacts"]:
    path = EVIDENCE / item["relative_path"]
    if file_sha256(path) != item["sha256"] or path.stat().st_size != item["size_bytes"]:
        raise RuntimeError(f"Blender artifact changed: {item['relative_path']}")
glb = EVIDENCE / next(
    item["relative_path"] for item in blender["artifacts"] if item["kind"] == "glb"
)
header = glb.read_bytes()[:12]
magic, version, declared_length = struct.unpack("<4sII", header)
if magic != b"glTF" or version != 2 or declared_length != glb.stat().st_size:
    raise RuntimeError("GLB header or declared length is invalid")
if (
    blender["boolean_modifier_count"] != request.chip_count
    or blender["triangle_count"] > request.triangle_budget
    or blender["uv_layer"] != "UVMap"
    or not blender["material_slots"]
):
    raise RuntimeError("Blender delivery violates its bounded geometry contract")
if (
    unreal["status"] != "reconciled"
    or unreal["updated_actor_count"] != 0
    or unreal["created_actor_count"] != 0
    or unreal["duplicate_asset_count"] != 0
    or unreal["convex_collision_count"] < 1
    or unreal["source_candidate_sha256_before"]
    != unreal["source_candidate_sha256_after"]
    or unreal["capture_status"] != "captured"
    or file_sha256(EVIDENCE / unreal["screenshot_path"])
    != unreal["screenshot_sha256"]
):
    raise RuntimeError("Unreal return did not reconcile cleanly")
print(
    json.dumps(
        {
            "schema": "artflow-m55-damage-verification/1",
            "status": "passed",
            "request_sha256": request.request_sha256,
            "comfy_field_sha256": comfy.field_sha256,
            "active_coverage": comfy.active_coverage,
            "protected_leakage": comfy.protected_leakage,
            "boolean_modifier_count": blender["boolean_modifier_count"],
            "triangle_count": blender["triangle_count"],
            "glb_bytes": glb.stat().st_size,
            "unreal_candidate": unreal["candidate_scene_path"],
            "duplicate_side_effect_count": 0,
        },
        ensure_ascii=False,
    )
)
