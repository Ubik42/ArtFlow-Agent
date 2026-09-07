from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOTS = {
    "model": ROOT / "artifacts/goal/m23-s1-blender-modeling",
    "pbr": ROOT / "artifacts/goal/m23-s2-blender-pbr",
    "layout": ROOT / "artifacts/goal/m23-s4-geometry-layout",
}


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize a fixed ArtFlow Unreal capture receipt.")
    parser.add_argument("--variant", choices=sorted(EVIDENCE_ROOTS), required=True)
    args = parser.parse_args()

    evidence_root = EVIDENCE_ROOTS[args.variant]
    receipt_path = evidence_root / "unreal-return-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    screenshot_path = evidence_root / receipt["screenshot_path"]
    if receipt.get("capture_status") != "requested":
        raise RuntimeError("Unreal capture receipt is not awaiting finalization")
    if not screenshot_path.is_file() or screenshot_path.stat().st_size == 0:
        raise RuntimeError("Unreal capture did not produce a non-empty screenshot")

    receipt["screenshot_sha256"] = file_sha256(screenshot_path)
    receipt["capture_status"] = "completed"
    receipt.pop("receipt_sha256", None)
    receipt["receipt_sha256"] = canonical_sha256(receipt)
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "ARTFLOW_BLENDER_UNREAL_RETURN "
        f"status={receipt['status']} mesh={receipt['static_mesh_path']} "
        f"candidate={receipt['candidate_scene_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
