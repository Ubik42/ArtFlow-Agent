import hashlib
import json
from pathlib import Path

from artflow_agent.scene_lifecycle import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts/goal/m24-s2-scene-lookdev"
RECEIPT_PATH = EVIDENCE / "unreal-lookdev-return-receipt.json"
receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
screenshot = EVIDENCE / receipt["screenshot_path"]
if (
    receipt["capture_status"] != "requested"
    or not screenshot.is_file()
    or screenshot.stat().st_size == 0
):
    raise RuntimeError("lookdev screenshot is not ready")
receipt["screenshot_sha256"] = hashlib.sha256(screenshot.read_bytes()).hexdigest()
receipt["capture_status"] = "completed"
receipt.pop("receipt_sha256", None)
receipt["receipt_sha256"] = canonical_sha256(receipt)
RECEIPT_PATH.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(
    f"ARTFLOW_LOOKDEV_FINALIZED status={receipt['status']} candidate={receipt['candidate_scene_path']}"
)
