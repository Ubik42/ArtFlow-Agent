from __future__ import annotations

import hashlib
import json
from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.blender_layout import (
    compile_geometry_layout_request,
    execute_geometry_layout,
)

ROOT = Path(__file__).resolve().parents[1]
PBR_ROOT = ROOT / "artifacts/goal/m23-s2-blender-pbr"
OUTPUT = ROOT / "artifacts/goal/m23-s4-geometry-layout"
BLENDER = Path("C:/Program Files/Blender Foundation/Blender 5.2/blender.exe")
EVENTS = ROOT / "artifacts/goal/m19-s1-candidate-work/agent-events.sqlite3"
RUN_ID = "unreal-artflow-ue-89ac07a74988b8dd2fca9295e141a6fd-ca79f77b487e"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


pbr_receipt = json.loads((PBR_ROOT / "pbr-assembly-receipt.json").read_text(encoding="utf-8"))
unreal_receipt = json.loads((PBR_ROOT / "unreal-return-receipt.json").read_text(encoding="utf-8"))
state = AgentEventStore(EVENTS).load(RUN_ID)
session = state.scene_sessions[-1]
twin = state.scene.digital_twin if state.scene else None
if twin is None:
    raise RuntimeError("Current Scene Session has no Digital Twin")
ground = next(actor for actor in twin.actors if actor.label == "ArtFlow_Ground")
editable = next(actor for actor in twin.actors if actor.label == "Editable_Form")
span_x = ground.bounds.maximum.x - ground.bounds.minimum.x
span_y = ground.bounds.maximum.y - ground.bounds.minimum.y
radius_cm = round(min(span_x, span_y) * 0.725, 1)
density = float(editable.pcg_components[0].exposed_parameters["density"])
support_count = round(radius_cm / 40.0)
height_variation = round(density * 0.8, 2)
seed = int(session.session_sha256[:8], 16) % 2_147_483_647
request = compile_geometry_layout_request(
    session_id=session.session_id,
    session_sha256=session.session_sha256,
    source_level_sha256=unreal_receipt["source_level_sha256_after"],
    source_blend_sha256=sha256(PBR_ROOT / "AF_WeatheredShrine_PBR.blend"),
    pbr_receipt_sha256=pbr_receipt["receipt_sha256"],
    radius_cm=radius_cm,
    support_count=support_count,
    height_variation=height_variation,
    seed=seed,
    output_stem="AF_ShrineCourtyard_GN",
)
receipt = execute_geometry_layout(
    request,
    project_root=ROOT,
    output_dir=OUTPUT,
    blender_executable=BLENDER,
)
print(receipt.model_dump_json(indent=2))
