from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from artflow_agent.scene_lifecycle import canonical_sha256

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts/goal/m23-s1-blender-modeling"
PBR = ROOT / "artifacts/goal/m8-s2-pbr-material"
OUTPUT = ROOT / "artifacts/goal/m23-s2-blender-pbr"
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
SCRIPT = ROOT / "integrations/blender/assemble_comfy_pbr.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


modeling = json.loads((SOURCE / "modeling-receipt.json").read_text(encoding="utf-8"))
pbr = json.loads((PBR / "validated-texture-set-receipt.json").read_text(encoding="utf-8"))
if pbr["status"] != "validated" or not all(item["accepted"] for item in pbr["artifacts"]):
    raise RuntimeError("ComfyUI PBR set is not validated")
channels = {"base_color", "normal", "roughness"}
textures = []
for item in pbr["artifacts"]:
    if item["channel"] in channels:
        path = (PBR / "validated" / item["relative_path"]).resolve()
        if sha256(path) != item["sha256"]:
            raise RuntimeError(f"PBR texture hash mismatch: {item['channel']}")
        textures.append({"channel": item["channel"], "path": str(path), "sha256": item["sha256"]})
unsigned = {
    "schema_id": "artflow-blender-pbr-assembly-request/1",
    "session_id": "scene-session-dc31f6ed0f4e",
    "modeling_receipt_sha256": modeling["receipt_sha256"],
    "pbr_receipt_sha256": sha256(PBR / "validated-texture-set-receipt.json"),
    "source_blend": str((SOURCE / "AF_WeatheredShrine.blend").resolve()),
    "source_blend_sha256": sha256(SOURCE / "AF_WeatheredShrine.blend"),
    "textures": sorted(textures, key=lambda item: item["channel"]),
    "output_stem": "AF_WeatheredShrine_PBR",
}
request = {**unsigned, "request_sha256": canonical_sha256(unsigned)}
OUTPUT.mkdir(parents=True, exist_ok=True)
(OUTPUT / "pbr-assembly-request.json").write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
subprocess.run([str(BLENDER), "--background", "--factory-startup", "--python", str(SCRIPT), "--", str(OUTPUT / "pbr-assembly-request.json"), str(OUTPUT)], check=True, cwd=ROOT, timeout=180)
print((OUTPUT / "pbr-assembly-receipt.json").read_text(encoding="utf-8"))
