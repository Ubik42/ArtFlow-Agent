from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from artflow_agent.pbr import canonical_sha256


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts" / "goal" / "m8-s2-pbr-material"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    request = json.loads((EVIDENCE / "unreal-pbr-return-request.json").read_text(encoding="utf-8"))
    receipt = json.loads((EVIDENCE / "unreal-pbr-return-receipt.json").read_text(encoding="utf-8"))
    validated = json.loads((EVIDENCE / "validated-texture-set-receipt.json").read_text(encoding="utf-8"))
    attempt_001 = json.loads(
        (EVIDENCE / "attempt-001" / "generation-validation-receipt.json").read_text(encoding="utf-8")
    )
    attempt_002 = json.loads(
        (EVIDENCE / "attempt-002" / "generation-validation-receipt.json").read_text(encoding="utf-8")
    )

    unsigned_request = dict(request)
    request_sha = unsigned_request.pop("request_sha256")
    assert canonical_sha256(unsigned_request) == request_sha
    unsigned_receipt = dict(receipt)
    receipt_sha = unsigned_receipt.pop("receipt_sha256")
    assert canonical_sha256(unsigned_receipt) == receipt_sha
    assert receipt["request_sha256"] == request_sha
    assert receipt["source_scene_sha256_before"] == receipt["source_scene_sha256_after"]
    assert receipt["protected_state_before"] == receipt["protected_state_after"]
    assert receipt["status"] == "reconciled"
    assert attempt_001["status"] == "semantic_invalid"
    assert attempt_002["status"] == "semantic_invalid"
    assert validated["status"] == "validated"

    texture_hashes = {}
    for texture in request["textures"]:
        path = ROOT / texture["path"]
        assert path.is_file()
        assert file_sha256(path) == texture["sha256"]
        texture_hashes[texture["channel"]] = texture["sha256"]

    candidate = ROOT / receipt["candidate_render_path"]
    assert file_sha256(candidate) == receipt["candidate_render_sha256"]
    baseline = EVIDENCE.parent / "m7-s2-scene-execution" / "candidate-beauty.png"
    before = Image.open(baseline).convert("RGB")
    after = Image.open(candidate).convert("RGB")
    assert before.size == after.size == (640, 360)
    difference = ImageChops.difference(before, after)
    target_mean = sum(ImageStat.Stat(difference.crop((375, 130, 490, 250))).mean) / 3
    protected_mean = sum(ImageStat.Stat(difference.crop((120, 105, 305, 295))).mean) / 3
    assert target_mean > protected_mean * 4

    report = {
        "schema_id": "m8-s2-independent-verification/1",
        "status": "verified",
        "request_sha256": request_sha,
        "receipt_sha256": receipt_sha,
        "texture_hashes": texture_hashes,
        "invalid_attempts_rejected": 2,
        "candidate_render_sha256": receipt["candidate_render_sha256"],
        "target_crop_mean_absolute_delta": round(target_mean, 6),
        "protected_crop_mean_absolute_delta": round(protected_mean, 6),
        "target_to_protected_delta_ratio": round(target_mean / protected_mean, 6),
        "source_scene_unchanged": True,
        "protected_state_unchanged": True,
        "replay_reconciled": True,
    }
    output = EVIDENCE / "independent-verification.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
