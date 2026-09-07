from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

from artflow_agent.scene_lifecycle import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts/goal/m32-s1-procedural-kit"
receipt_path = OUTPUT / "unreal-procedural-kit-return-receipt.json"
receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
screenshot = OUTPUT / receipt["screenshot_path"]
with Image.open(screenshot) as image:
    if image.size != (1280, 720):
        raise RuntimeError("Unreal procedural-kit capture has unexpected dimensions")
receipt["screenshot_sha256"] = hashlib.sha256(screenshot.read_bytes()).hexdigest()
receipt["capture_status"] = "completed"
receipt.pop("receipt_sha256", None)
receipt["receipt_sha256"] = canonical_sha256(receipt)
receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt, ensure_ascii=False))
