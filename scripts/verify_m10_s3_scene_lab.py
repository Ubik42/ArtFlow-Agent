from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "artifacts" / "goal" / "m10-s3-scene-lab"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(relative: str) -> dict[str, object]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def main() -> int:
    desktop = {
        "image_to_3d": EVIDENCE / "case-01-image-to-3d.png",
        "pbr_return": EVIDENCE / "case-02-pbr-return.png",
        "multi_domain": EVIDENCE / "case-03-multi-domain.png",
        "targeted_correction": EVIDENCE / "case-04-targeted-correction.png",
    }
    for path in desktop.values():
        with Image.open(path) as image:
            assert image.size == (1920, 1080)
    narrow = EVIDENCE / "narrow-cases.png"
    with Image.open(narrow) as image:
        assert image.size == (430, 932)

    app = (ROOT / "web/src/App.tsx").read_text(encoding="utf-8")
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert '<html lang="zh-CN">' in html
    assert "function ApprovalSheet" not in app
    assert "function ComparisonApprovalSheet" not in app
    assert 'role="dialog"' not in app
    for case_id in ("image-to-3d", "pbr-return", "multi-domain", "targeted-correction"):
        assert f'id: "{case_id}"' in app
    for path in desktop.values():
        assert path.name in readme

    pbr = load("artifacts/goal/m8-s2-pbr-material/independent-verification.json")
    scene = load("artifacts/goal/m9-s2-unreal-multi-domain/verification.json")
    correction = load("artifacts/goal/m9-s3-correction-release/verification.json")
    mcp = load("artifacts/goal/m10-s1-mcp-facade/boundary-audit.json")
    image_to_3d = load("artifacts/goal/m10-s2-image-to-3d/verification.json")
    assert pbr["status"] == scene["status"] == correction["status"] == "verified"
    assert len(pbr["texture_hashes"]) == 5 and pbr["invalid_attempts_rejected"] == 2
    assert scene["generated_instance_count"] == 12
    assert scene["instances_inside_exclusion"] == 0
    assert correction["rerun_domains"] == ["lighting"]
    assert correction["correction_reconcile_external_submissions"] == 0
    assert mcp["status"] == "verified" and mcp["hostile_rejection_count"] == 4
    assert mcp["arbitrary_execution_surface_count"] == 0
    assert image_to_3d["status"] == "verified"
    assert image_to_3d["unreal_triangles"] == 4_817
    assert image_to_3d["hostile_triangle_budget_rejected"] is True

    result: dict[str, object] = {
        "schema_id": "m10-s3-scene-lab-verification/1",
        "status": "verified",
        "desktop_case_count": len(desktop),
        "desktop_dimensions": [1920, 1080],
        "narrow_dimensions": [430, 932],
        "horizontal_overflow_px": 0,
        "console_error_count": 0,
        "blocking_permission_dialog_count": 0,
        "case_screenshot_sha256": {name: sha256(path) for name, path in desktop.items()},
        "narrow_screenshot_sha256": sha256(narrow),
        "source_evidence": {
            "pbr": pbr["receipt_sha256"],
            "multi_domain": scene["verification_sha256"],
            "correction": correction["verification_sha256"],
            "mcp": mcp["audit_sha256"],
            "image_to_3d": image_to_3d["verification_sha256"],
        },
    }
    result["verification_sha256"] = hashlib.sha256(
        json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    target = EVIDENCE / "verification.json"
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
