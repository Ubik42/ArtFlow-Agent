from __future__ import annotations

import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


class SetDressingBounds(StrictContract):
    min_m: list[float] = Field(min_length=3, max_length=3)
    max_m: list[float] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def verify_bounds(self) -> SetDressingBounds:
        if any(not math.isfinite(value) for value in [*self.min_m, *self.max_m]):
            raise ValueError("set-dressing bounds must be finite")
        if any(low >= high for low, high in zip(self.min_m, self.max_m, strict=True)):
            raise ValueError("set-dressing bounds are inverted")
        return self


class BlenderSetDressingRequest(StrictContract):
    schema_id: Literal["artflow-blender-set-dressing-request/1"] = (
        "artflow-blender-set-dressing-request/1"
    )
    request_id: str = Field(pattern=r"^set-dressing-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    session_sha256: str = Field(pattern=SHA256_PATTERN)
    source_level_sha256: str = Field(pattern=SHA256_PATTERN)
    surface_request_sha256: str = Field(pattern=SHA256_PATTERN)
    surface_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.rigidbody.rubble_settle.v1"] = (
        "blender.rigidbody.rubble_settle.v1"
    )
    prototype: Literal["AF_Rubble_01"] = "AF_Rubble_01"
    bounds: SetDressingBounds
    object_count: int = Field(ge=8, le=16)
    seed: int = Field(ge=0, le=2**31 - 1)
    frame_end: int = Field(ge=72, le=120)
    max_final_motion_m: float = Field(gt=0, le=0.05)
    min_center_separation_m: float = Field(gt=0, le=0.2)
    output_stem: Literal["AF_Courtyard_SettledRubble"] = "AF_Courtyard_SettledRubble"
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_request(self) -> BlenderSetDressingRequest:
        actual = canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"}))
        if actual != self.request_sha256:
            raise ValueError("set-dressing request fingerprint mismatch")
        return self


class SettledTransform(StrictContract):
    instance_id: str = Field(pattern=r"^rubble-[0-9]{2}$")
    location_m: list[float] = Field(min_length=3, max_length=3)
    rotation_deg: list[float] = Field(min_length=3, max_length=3)
    scale: list[float] = Field(min_length=3, max_length=3)


class SetDressingArtifact(StrictContract):
    kind: Literal["blend", "preview", "prototype_glb", "transform_manifest"]
    relative_path: str = Field(pattern=r"^[A-Za-z0-9_./-]+$")
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class BlenderSetDressingReceipt(StrictContract):
    schema_id: Literal["artflow-blender-set-dressing-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.rigidbody.rubble_settle.v1"]
    status: Literal["succeeded"]
    blender_version: str
    instance_count: int = Field(ge=8, le=16)
    settled_frame: int = Field(ge=72, le=120)
    max_final_motion_m: float = Field(ge=0, le=0.05)
    min_center_separation_m: float = Field(gt=0)
    transforms: list[SettledTransform] = Field(min_length=8, max_length=16)
    artifacts: list[SetDressingArtifact] = Field(min_length=4, max_length=4)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderSetDressingReceipt:
        if len(self.transforms) != self.instance_count:
            raise ValueError("settled transform count mismatch")
        if {item.kind for item in self.artifacts} != {
            "blend", "preview", "prototype_glb", "transform_manifest"
        }:
            raise ValueError("set-dressing receipt is missing an artifact")
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("set-dressing receipt fingerprint mismatch")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_set_dressing_request(
    *, session_id: str, session_sha256: str, source_level_sha256: str,
    surface_request_path: Path, surface_receipt_path: Path, source_blend_path: Path,
) -> BlenderSetDressingRequest:
    surface_request = json.loads(surface_request_path.read_text(encoding="utf-8"))
    surface_receipt = json.loads(surface_receipt_path.read_text(encoding="utf-8"))
    blend_artifact = next(item for item in surface_receipt["artifacts"] if item["kind"] == "blend")
    if surface_receipt["request_sha256"] != surface_request["request_sha256"]:
        raise ValueError("surface request and receipt do not match")
    if file_sha256(source_blend_path) != blend_artifact["sha256"]:
        raise ValueError("surface blend identity drifted")
    unsigned = {
        "schema_id": "artflow-blender-set-dressing-request/1",
        "session_id": session_id,
        "session_sha256": session_sha256,
        "source_level_sha256": source_level_sha256,
        "surface_request_sha256": surface_request["request_sha256"],
        "surface_receipt_sha256": surface_receipt["receipt_sha256"],
        "source_blend_sha256": file_sha256(source_blend_path),
        "capability_id": "blender.rigidbody.rubble_settle.v1",
        "prototype": "AF_Rubble_01",
        "bounds": {"min_m": [-4.8, -4.8, 0.0], "max_m": [4.8, 4.8, 4.0]},
        "object_count": 12,
        "seed": 260907,
        "frame_end": 96,
        "max_final_motion_m": 0.03,
        "min_center_separation_m": 0.08,
        "output_stem": "AF_Courtyard_SettledRubble",
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"set-dressing-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return BlenderSetDressingRequest.model_validate(unsigned)


def verify_set_dressing(
    request: BlenderSetDressingRequest, receipt: BlenderSetDressingReceipt, output_dir: Path
) -> None:
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("set-dressing receipt belongs to another request")
    low, high = request.bounds.min_m, request.bounds.max_m
    for transform in receipt.transforms:
        values = [*transform.location_m, *transform.rotation_deg, *transform.scale]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("set-dressing transform is not finite")
        if not all(low[i] <= transform.location_m[i] <= high[i] for i in range(3)):
            raise ValueError(f"set-dressing instance escaped bounds: {transform.instance_id}")
    if receipt.max_final_motion_m > request.max_final_motion_m:
        raise ValueError("set-dressing simulation did not settle")
    if receipt.min_center_separation_m < request.min_center_separation_m:
        raise ValueError("set-dressing instances overlap beyond the registered tolerance")
    for artifact in receipt.artifacts:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir.resolve() not in path.parents or file_sha256(path) != artifact.sha256:
            raise ValueError(f"set-dressing artifact identity mismatch: {artifact.kind}")


def execute_set_dressing(
    request: BlenderSetDressingRequest, *, project_root: Path, source_blend_path: Path,
    output_dir: Path, blender_executable: Path, timeout_seconds: int = 300,
) -> BlenderSetDressingReceipt:
    project_root, output_dir = project_root.resolve(), output_dir.resolve()
    if project_root not in output_dir.parents:
        raise ValueError("set-dressing output must stay inside the project")
    if file_sha256(source_blend_path) != request.source_blend_sha256:
        raise ValueError("set-dressing source identity mismatch")
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "set-dressing-request.json"
    request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
    script = project_root / "integrations/blender/settle_rubble.py"
    subprocess.run(
        [str(blender_executable), "--background", "--factory-startup", "--python", str(script),
         "--", str(request_path), str(output_dir), str(source_blend_path)],
        check=True, cwd=project_root, timeout=timeout_seconds,
    )
    receipt_path = output_dir / "set-dressing-receipt.json"
    if not receipt_path.is_file():
        raise RuntimeError("Blender exited without a set-dressing receipt")
    receipt = BlenderSetDressingReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    verify_set_dressing(request, receipt, output_dir)
    return receipt
