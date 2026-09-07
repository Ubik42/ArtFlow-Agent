from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "artifacts/goal/m23-s5-camera-light"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    receipt_path = EVIDENCE_ROOT / "unreal-shot-return-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    screenshot_path = EVIDENCE_ROOT / receipt["screenshot_path"]
    if receipt.get("capture_status") != "requested":
        raise RuntimeError("Unreal shot capture is not awaiting finalization")
    if not screenshot_path.is_file() or screenshot_path.stat().st_size == 0:
        raise RuntimeError("Unreal shot capture did not produce a non-empty screenshot")
    receipt["screenshot_sha256"] = file_sha256(screenshot_path)
    receipt["capture_status"] = "completed"
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ARTFLOW_UNREAL_SHOT_RETURN "
        f"status={receipt['status']} candidate={receipt['candidate_scene_path']} "
        f"lights={len(receipt['applied_lights'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
