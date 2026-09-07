from __future__ import annotations

import hashlib
import json
from pathlib import Path

from artflow_agent.blender_shot import compile_blender_shot_request, execute_blender_shot

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "artifacts/goal/m23-s5-camera-light"
LAYOUT_ROOT = ROOT / "artifacts/goal/m23-s4-geometry-layout"
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


source = json.loads((SOURCE_ROOT / "unreal-camera-light-source.json").read_text(encoding="utf-8"))
layout = json.loads((LAYOUT_ROOT / "layout-receipt.json").read_text(encoding="utf-8"))
request = compile_blender_shot_request(
    session_id=source["session_id"],
    session_sha256=source["session_sha256"],
    source_level_sha256=source["source_level_sha256"],
    source_receipt_sha256=source["receipt_sha256"],
    layout_receipt_sha256=layout["receipt_sha256"],
    source_blend_sha256=sha256(LAYOUT_ROOT / "AF_ShrineCourtyard_GN.blend"),
    camera=source["camera"],
    subject_origin_cm=[450.0, 0.0, 0.0],
    source_lights=source["directional_lights"],
    proposed_rig=[
        {"role": "key", "rotation_deg": [-38.0, -32.0, 0.0], "intensity_lux": 3.2, "temperature_kelvin": 5200.0, "cast_shadows": True},
        {"role": "fill", "rotation_deg": [-58.0, 118.0, 0.0], "intensity_lux": 0.65, "temperature_kelvin": 8800.0, "cast_shadows": True},
        {"role": "rim", "rotation_deg": [-22.0, 168.0, 0.0], "intensity_lux": 1.4, "temperature_kelvin": 7600.0, "cast_shadows": True},
    ],
    output_stem="AF_ShrineCourtyard_Shot",
)
receipt = execute_blender_shot(
    request,
    project_root=ROOT,
    output_dir=SOURCE_ROOT,
    blender_executable=BLENDER,
)
print(receipt.model_dump_json(indent=2))
