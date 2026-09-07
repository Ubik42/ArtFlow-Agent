import hashlib
import json
from pathlib import Path

from PIL import Image

root = Path(__file__).resolve().parents[1] / "artifacts/goal/m28-s1-set-dressing"
path = root / "unreal-set-dressing-return-receipt.json"
receipt = json.loads(path.read_text(encoding="utf-8"))
screenshot = root / receipt["screenshot_path"]
with Image.open(screenshot) as image:
    if image.size != (1280, 720):
        raise RuntimeError("set-dressing capture dimensions are invalid")
receipt["screenshot_sha256"] = hashlib.sha256(screenshot.read_bytes()).hexdigest()
receipt["capture_status"] = "completed"
receipt.pop("receipt_sha256", None)
receipt["receipt_sha256"] = hashlib.sha256(json.dumps(receipt, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"ARTFLOW_SET_DRESSING_FINALIZED status={receipt['status']}")
