from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

from PIL import Image
from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.blender_shot import ShotRigLight, UnrealCameraFact
from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256

MaterialTarget = Literal["M_AF_Stone", "M_AF_Weathering", "M_AF_Inlay"]


class MaterialTint(StrictContract):
    target: MaterialTarget
    color_srgb: list[float] = Field(min_length=3, max_length=3)
    blend: float = Field(ge=0.1, le=0.65)

    @model_validator(mode="after")
    def validate_color(self) -> MaterialTint:
        if any(channel < 0 or channel > 1 for channel in self.color_srgb):
            raise ValueError("material tint channels must be normalized sRGB")
        return self


class SceneLookdevRequest(StrictContract):
    schema_id: Literal["artflow-scene-lookdev-request/1"] = "artflow-scene-lookdev-request/1"
    request_id: str = Field(pattern=r"^scene-lookdev-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    session_sha256: str = Field(pattern=SHA256_PATTERN)
    source_level_sha256: str = Field(pattern=SHA256_PATTERN)
    conditioning_request_sha256: str = Field(pattern=SHA256_PATTERN)
    conditioning_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    accepted_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    source_shot_request_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.lookdev.scene_target.v1"] = "blender.lookdev.scene_target.v1"
    camera: UnrealCameraFact
    material_tints: list[MaterialTint] = Field(min_length=3, max_length=3)
    light_rig: list[ShotRigLight] = Field(min_length=3, max_length=3)
    output_stem: Literal["AF_ShrineCourtyard_Lookdev"] = "AF_ShrineCourtyard_Lookdev"
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_request(self) -> SceneLookdevRequest:
        if [item.target for item in self.material_tints] != [
            "M_AF_Stone",
            "M_AF_Weathering",
            "M_AF_Inlay",
        ]:
            raise ValueError("lookdev material targets are not the registered set")
        if [item.role for item in self.light_rig] != ["key", "fill", "rim"]:
            raise ValueError("lookdev light roles must be key, fill and rim")
        actual = canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"}))
        if actual != self.request_sha256:
            raise ValueError("lookdev request fingerprint mismatch")
        return self


class LookdevArtifact(StrictContract):
    kind: Literal["blend", "preview"]
    relative_path: str = Field(pattern=r"^[A-Za-z0-9_./-]+$")
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class BlenderLookdevReceipt(StrictContract):
    schema_id: Literal["artflow-blender-lookdev-receipt/1"]
    request_id: str
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.lookdev.scene_target.v1"]
    status: Literal["succeeded"]
    blender_version: str
    camera_label: Literal["ArtFlow_Shot_Camera"]
    material_targets: list[MaterialTarget] = Field(min_length=3, max_length=3)
    light_roles: list[Literal["key", "fill", "rim"]] = Field(min_length=3, max_length=3)
    artifacts: list[LookdevArtifact] = Field(min_length=2, max_length=2)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderLookdevReceipt:
        if (
            canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"}))
            != self.receipt_sha256
        ):
            raise ValueError("Blender lookdev receipt fingerprint mismatch")
        return self


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _palette(image_path: Path) -> list[list[float]]:
    image = Image.open(image_path).convert("RGB")
    image.thumbnail((96, 96))
    quantized = image.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()
    colors = quantized.getcolors() or []
    weighted = []
    for count, index in colors:
        rgb = palette[index * 3 : index * 3 + 3]
        luminance = 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]
        saturation = max(rgb) - min(rgb)
        weighted.append((count, luminance, saturation, rgb))
    weighted.sort(key=lambda item: item[1])
    dark = max(weighted[: max(1, len(weighted) // 2)], key=lambda item: item[0])[3]
    light = max(weighted[len(weighted) // 2 :], key=lambda item: item[0])[3]
    accent = max(weighted, key=lambda item: item[2] * (item[0] ** 0.35))[3]
    return [[round(channel / 255.0, 4) for channel in color] for color in (light, dark, accent)]


def compile_scene_lookdev_request(
    *,
    session_id: str,
    session_sha256: str,
    source_level_sha256: str,
    conditioning_request_path: Path,
    conditioning_receipt_path: Path,
    accepted_artifact_path: Path,
    shot_request_path: Path,
    source_blend_path: Path,
) -> SceneLookdevRequest:
    conditioning_request = json.loads(conditioning_request_path.read_text(encoding="utf-8"))
    conditioning_receipt = json.loads(conditioning_receipt_path.read_text(encoding="utf-8"))
    shot = json.loads(shot_request_path.read_text(encoding="utf-8"))
    artifact_hash = file_sha256(accepted_artifact_path)
    if conditioning_receipt["request_sha256"] != conditioning_request["request_sha256"]:
        raise ValueError("conditioning request and receipt do not match")
    if conditioning_receipt["artifact_sha256"] != artifact_hash:
        raise ValueError("accepted visual target identity drifted")
    if shot["source_level_sha256"] != source_level_sha256:
        raise ValueError("shot and current scene do not match")
    light, dark, accent = _palette(accepted_artifact_path)
    material_tints = [
        {"target": "M_AF_Stone", "color_srgb": light, "blend": 0.42},
        {"target": "M_AF_Weathering", "color_srgb": dark, "blend": 0.5},
        {"target": "M_AF_Inlay", "color_srgb": accent, "blend": 0.58},
    ]
    # The accepted target is explicitly warm-key / cold-fill. Only this finite preset is compiled.
    light_rig = [
        {
            "role": "key",
            "rotation_deg": [-38.0, -32.0, 0.0],
            "intensity_lux": 4.4,
            "temperature_kelvin": 4300.0,
            "cast_shadows": True,
        },
        {
            "role": "fill",
            "rotation_deg": [-58.0, 118.0, 0.0],
            "intensity_lux": 0.48,
            "temperature_kelvin": 9200.0,
            "cast_shadows": True,
        },
        {
            "role": "rim",
            "rotation_deg": [-22.0, 168.0, 0.0],
            "intensity_lux": 1.65,
            "temperature_kelvin": 6800.0,
            "cast_shadows": True,
        },
    ]
    unsigned = {
        "schema_id": "artflow-scene-lookdev-request/1",
        "session_id": session_id,
        "session_sha256": session_sha256,
        "source_level_sha256": source_level_sha256,
        "conditioning_request_sha256": conditioning_request["request_sha256"],
        "conditioning_receipt_sha256": file_sha256(conditioning_receipt_path),
        "accepted_artifact_sha256": artifact_hash,
        "source_shot_request_sha256": shot["request_sha256"],
        "source_blend_sha256": file_sha256(source_blend_path),
        "capability_id": "blender.lookdev.scene_target.v1",
        "camera": shot["camera"],
        "material_tints": material_tints,
        "light_rig": light_rig,
        "output_stem": "AF_ShrineCourtyard_Lookdev",
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"scene-lookdev-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return SceneLookdevRequest.model_validate(unsigned)


def execute_blender_lookdev(
    request: SceneLookdevRequest,
    *,
    project_root: Path,
    source_blend_path: Path,
    output_dir: Path,
    blender_executable: Path,
    timeout_seconds: int = 180,
) -> BlenderLookdevReceipt:
    project_root, output_dir = project_root.resolve(), output_dir.resolve()
    if project_root not in output_dir.parents:
        raise ValueError("lookdev output must stay inside the project")
    if file_sha256(source_blend_path) != request.source_blend_sha256:
        raise ValueError("lookdev source blend identity mismatch")
    output_dir.mkdir(parents=True, exist_ok=True)
    request_path = output_dir / "lookdev-request.json"
    request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
    script = project_root / "integrations/blender/apply_scene_lookdev.py"
    subprocess.run(
        [
            str(blender_executable),
            "--background",
            "--factory-startup",
            "--python",
            str(script),
            "--",
            str(request_path),
            str(output_dir),
            str(source_blend_path),
        ],
        check=True,
        cwd=project_root,
        timeout=timeout_seconds,
    )
    receipt_path = output_dir / "lookdev-receipt.json"
    receipt = BlenderLookdevReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("Blender lookdev receipt belongs to another request")
    for artifact in receipt.artifacts:
        path = (output_dir / artifact.relative_path).resolve()
        if output_dir not in path.parents or file_sha256(path) != artifact.sha256:
            raise ValueError("Blender lookdev artifact identity mismatch")
    return receipt
