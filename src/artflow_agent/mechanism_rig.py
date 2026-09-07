from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class MechanismJointSpec(StrictContract):
    joint_id: Literal["hinge_left", "hinge_right"]
    parent_bone: Literal["root"]
    axis: Literal["Z"]
    closed_angle_deg: float = Field(ge=-1, le=1)
    open_angle_deg: float = Field(ge=-75, le=75)


class MechanismRigRequest(StrictContract):
    schema_id: Literal["artflow-mechanism-rig-request/1"] = "artflow-mechanism-rig-request/1"
    request_id: str = Field(pattern=r"^mechanism-rig-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    visual_target_path: str
    visual_target_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    mechanism_type: Literal["articulated_gate_v1"]
    width_cm: int = Field(ge=300, le=800)
    height_cm: int = Field(ge=220, le=600)
    depth_cm: int = Field(ge=12, le=80)
    frame_start: Literal[1]
    frame_open: int = Field(ge=12, le=48)
    frame_end: int = Field(ge=36, le=96)
    fps: Literal[24, 30]
    joints: list[MechanismJointSpec] = Field(min_length=2, max_length=2)
    triangle_budget: int = Field(ge=100, le=10000)
    blender_capability_id: Literal["blender.armature.articulated_gate.v1"]
    unreal_capability_id: Literal["unreal.skeletal.mechanism_import.v1"]
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> MechanismRigRequest:
        if {joint.joint_id for joint in self.joints} != {"hinge_left", "hinge_right"}:
            raise ValueError("mechanism requires the registered two-joint catalog")
        angles = {joint.joint_id: joint.open_angle_deg for joint in self.joints}
        if not (angles["hinge_left"] > 0 and angles["hinge_right"] < 0):
            raise ValueError("gate joints must open away from the center")
        if not self.frame_start < self.frame_open < self.frame_end:
            raise ValueError("mechanism action frames must be ordered")
        if (
            canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"}))
            != self.request_sha256
        ):
            raise ValueError("mechanism request fingerprint mismatch")
        return self


def compile_mechanism_rig_request(*, root: Path, session_id: str) -> MechanismRigRequest:
    root = root.resolve()
    visual = root / "artifacts/goal/m24-s1-scene-conditioning/depth-guided-candidate.png"
    spline = json.loads(
        (
            root
            / "artifacts/goal/m49-s1-spline-infrastructure/unreal-spline-infrastructure-receipt.json"
        ).read_text(encoding="utf-8")
    )
    source = (
        root
        / "integrations/unreal/ArtFlowBridgeHost/Content"
        / (spline["candidate_scene_path"].removeprefix("/Game/") + ".umap")
    )
    unsigned = {
        "schema_id": "artflow-mechanism-rig-request/1",
        "session_id": session_id,
        "visual_target_path": visual.as_posix(),
        "visual_target_sha256": file_sha256(visual),
        "source_candidate_scene_path": spline["candidate_scene_path"],
        "source_candidate_sha256": file_sha256(source),
        "mechanism_type": "articulated_gate_v1",
        "width_cm": 520,
        "height_cm": 360,
        "depth_cm": 28,
        "frame_start": 1,
        "frame_open": 24,
        "frame_end": 48,
        "fps": 24,
        "joints": [
            {
                "joint_id": "hinge_left",
                "parent_bone": "root",
                "axis": "Z",
                "closed_angle_deg": 0.0,
                "open_angle_deg": 70.0,
            },
            {
                "joint_id": "hinge_right",
                "parent_bone": "root",
                "axis": "Z",
                "closed_angle_deg": 0.0,
                "open_angle_deg": -70.0,
            },
        ],
        "triangle_budget": 5000,
        "blender_capability_id": "blender.armature.articulated_gate.v1",
        "unreal_capability_id": "unreal.skeletal.mechanism_import.v1",
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"mechanism-rig-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return MechanismRigRequest.model_validate(unsigned)


def execute_blender_mechanism(
    request: MechanismRigRequest, *, root: Path, output_dir: Path, blender_executable: Path
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "mechanism-rig-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    subprocess.run(
        [
            str(blender_executable),
            "--background",
            "--factory-startup",
            "--python",
            str(root / "integrations/blender/author_articulated_gate.py"),
            "--",
            str(request_path),
            str(output_dir),
        ],
        cwd=root,
        check=True,
        timeout=360,
    )
    receipt_path = output_dir / "blender-mechanism-rig-receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError("Blender mechanism process produced no terminal receipt")
    return json.loads(receipt_path.read_text(encoding="utf-8"))
