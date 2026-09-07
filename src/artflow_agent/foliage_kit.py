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


class FoliageSpecies(StrictContract):
    species_id: Literal["reed", "fern", "broadleaf"]
    max_height_cm: int = Field(ge=40, le=240)
    blade_count: int = Field(ge=3, le=12)
    wind_strength: float = Field(ge=0.05, le=0.7)
    wind_speed: float = Field(ge=0.2, le=2.0)


class FoliageKitRequest(StrictContract):
    schema_id: Literal["artflow-foliage-kit-request/1"] = "artflow-foliage-kit-request/1"
    request_id: str = Field(pattern=r"^foliage-kit-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    biome_mask_path: str
    biome_mask_sha256: str = Field(pattern=SHA256_PATTERN)
    biome_points_path: str
    biome_points_sha256: str = Field(pattern=SHA256_PATTERN)
    terrain_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    blender_capability_id: Literal["blender.geometry_nodes.biome_foliage_kit.v1"]
    unreal_capability_id: Literal["unreal.pcg.biome_foliage_wind.v1"]
    species: list[FoliageSpecies] = Field(min_length=3, max_length=3)
    instance_budget: int = Field(ge=3, le=48)
    triangle_budget_per_variant: int = Field(ge=64, le=4000)
    lod_policy: Literal["lod1-at-most-60-percent-triangles"]
    collision_policy: Literal["explicit-box-proxy-per-variant"]
    seed: int = Field(ge=0, le=2**31 - 1)
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> FoliageKitRequest:
        if {item.species_id for item in self.species} != {"reed", "fern", "broadleaf"}:
            raise ValueError("foliage request must contain the three registered species")
        actual = canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"}))
        if actual != self.request_sha256:
            raise ValueError("foliage request fingerprint mismatch")
        return self


def compile_foliage_kit_request(*, root: Path, session_id: str) -> FoliageKitRequest:
    root = root.resolve()
    m42 = root / "artifacts/goal/m42-s1-terrain-biome"
    field = json.loads((m42 / "comfy-terrain-fields-receipt.json").read_text(encoding="utf-8"))
    terrain = json.loads((m42 / "unreal-biome-terrain-receipt.json").read_text(encoding="utf-8"))
    mask = m42 / "biome-mask.png"
    points = m42 / "biome-pcg-points.json"
    if terrain.get("status") not in {"generated", "reconciled"}:
        raise ValueError("foliage route requires the completed M42 terrain candidate")
    if file_sha256(mask) != field["biome_mask_sha256"]:
        raise ValueError("registered biome mask identity drifted")
    point_data = json.loads(points.read_text(encoding="utf-8"))
    if point_data.get("request_sha256") != terrain["request_sha256"]:
        raise ValueError("biome points do not belong to the terrain candidate")
    source_file = root / "integrations/unreal/ArtFlowBridgeHost/Content" / (
        terrain["candidate_scene_path"].removeprefix("/Game/") + ".umap"
    )
    if not source_file.is_file():
        raise ValueError("registered terrain candidate is unavailable")
    unsigned = {
        "schema_id": "artflow-foliage-kit-request/1",
        "session_id": session_id,
        "biome_mask_path": mask.as_posix(),
        "biome_mask_sha256": file_sha256(mask),
        "biome_points_path": points.as_posix(),
        "biome_points_sha256": file_sha256(points),
        "terrain_receipt_sha256": file_sha256(m42 / "unreal-biome-terrain-receipt.json"),
        "source_candidate_scene_path": terrain["candidate_scene_path"],
        "source_candidate_sha256": file_sha256(source_file),
        "blender_capability_id": "blender.geometry_nodes.biome_foliage_kit.v1",
        "unreal_capability_id": "unreal.pcg.biome_foliage_wind.v1",
        "species": [
            {"species_id": "reed", "max_height_cm": 180, "blade_count": 9, "wind_strength": 0.24, "wind_speed": 0.75},
            {"species_id": "fern", "max_height_cm": 105, "blade_count": 7, "wind_strength": 0.18, "wind_speed": 0.55},
            {"species_id": "broadleaf", "max_height_cm": 135, "blade_count": 5, "wind_strength": 0.31, "wind_speed": 0.42},
        ],
        "instance_budget": len(point_data["points"]),
        "triangle_budget_per_variant": 2400,
        "lod_policy": "lod1-at-most-60-percent-triangles",
        "collision_policy": "explicit-box-proxy-per-variant",
        "seed": 450907,
    }
    provisional = canonical_sha256(unsigned)
    unsigned["request_id"] = f"foliage-kit-{provisional[:16]}"
    unsigned["request_sha256"] = canonical_sha256(unsigned)
    return FoliageKitRequest.model_validate(unsigned)


def execute_blender_foliage(request: FoliageKitRequest, *, root: Path, output_dir: Path,
                            blender_executable: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    for value, expected in ((request.biome_mask_path, request.biome_mask_sha256),
                            (request.biome_points_path, request.biome_points_sha256)):
        if file_sha256(Path(value)) != expected:
            raise ValueError("registered foliage input identity drifted")
    request_path = output_dir / "foliage-kit-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    subprocess.run([
        str(blender_executable), "--background", "--factory-startup", "--python",
        str(root / "integrations/blender/author_biome_foliage_kit.py"), "--",
        str(request_path), str(output_dir),
    ], check=True, cwd=root, timeout=360)
    receipt = json.loads((output_dir / "blender-foliage-kit-receipt.json").read_text(encoding="utf-8"))
    if receipt.get("request_sha256") != request.request_sha256 or len(receipt.get("variants", [])) != 3:
        raise ValueError("Blender foliage receipt is incomplete or belongs to another request")
    for artifact in receipt["artifacts"]:
        if file_sha256(output_dir / artifact["relative_path"]) != artifact["sha256"]:
            raise ValueError(f"foliage artifact identity drifted: {artifact['relative_path']}")
    return receipt
