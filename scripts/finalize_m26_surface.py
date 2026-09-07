from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/goal/m26-s1-surface-bake"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


receipt_path = EVIDENCE / "unreal-surface-return-receipt.json"
receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
screenshot = EVIDENCE / receipt["screenshot_path"]
with Image.open(screenshot) as image:
    if image.size != (1280, 720):
        raise RuntimeError("Unreal surface capture dimensions are invalid")
receipt["screenshot_sha256"] = sha256(screenshot)
receipt["capture_status"] = "completed"
receipt.pop("receipt_sha256", None)
receipt["receipt_sha256"] = canonical(receipt)
receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"ARTFLOW_SURFACE_FINALIZED status={receipt['status']} candidate={receipt['candidate_scene_path']}")
