from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from artflow_agent.contracts.scene_delta import SHA256_PATTERN, StrictContract
from artflow_agent.scene_lifecycle import canonical_sha256


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SimulationCacheRequest(StrictContract):
    schema_id: Literal["artflow-simulation-cache-request/1"] = "artflow-simulation-cache-request/1"
    request_id: str = Field(pattern=r"^simulation-cache-[a-f0-9]{16}$")
    session_id: str = Field(pattern=r"^scene-session-[a-f0-9]{12}$")
    terrain_receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    source_candidate_scene_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+$")
    source_candidate_sha256: str = Field(pattern=SHA256_PATTERN)
    source_blend_path: str
    source_blend_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.cache.wind_veil.v1"]
    consumer_capability_id: Literal["unreal.geometry_cache.sequence.v1"]
    frame_start: Literal[1]
    frame_end: Literal[72]
    frame_rate: Literal[24]
    mesh_columns: int = Field(ge=16, le=64)
    mesh_rows: int = Field(ge=8, le=32)
    amplitude_m: float = Field(gt=0.05, le=0.8)
    max_cache_bytes: int = Field(gt=0, le=64 * 1024 * 1024)
    output_stem: Literal["AF_WindVeil_Cache"]
    sequence_asset_path: str = Field(pattern=r"^/Game/[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+$")
    request_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_identity(self) -> SimulationCacheRequest:
        if canonical_sha256(self.model_dump(mode="json", exclude={"request_sha256"})) != self.request_sha256:
            raise ValueError("simulation-cache request fingerprint mismatch")
        return self


class SimulationArtifact(StrictContract):
    kind: Literal["blend", "alembic", "preview_start", "preview_middle", "preview_end"]
    relative_path: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0)


class BlenderSimulationCacheReceipt(StrictContract):
    schema_id: Literal["artflow-blender-simulation-cache-receipt/1"]
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    capability_id: Literal["blender.cache.wind_veil.v1"]
    status: Literal["succeeded"]
    blender_version: str
    object_name: Literal["AF_WindVeil"]
    frame_range: list[int] = Field(min_length=2, max_length=2)
    sample_count: Literal[72]
    vertex_count: int = Field(ge=128, le=4096)
    face_count: int = Field(ge=100, le=4096)
    max_displacement_m: float = Field(gt=0, le=0.8)
    artifacts: list[SimulationArtifact] = Field(min_length=5, max_length=5)
    elapsed_seconds: float = Field(gt=0)
    completed_at: AwareDatetime
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def verify_receipt(self) -> BlenderSimulationCacheReceipt:
        if self.frame_range != [1, 72]:
            raise ValueError("simulation cache returned another frame range")
        expected = {"blend", "alembic", "preview_start", "preview_middle", "preview_end"}
        if {item.kind for item in self.artifacts} != expected:
            raise ValueError("simulation cache receipt is incomplete")
        if canonical_sha256(self.model_dump(mode="json", exclude={"receipt_sha256"})) != self.receipt_sha256:
            raise ValueError("simulation-cache receipt fingerprint mismatch")
        return self


def compile_simulation_cache_request(*, project_root: Path) -> SimulationCacheRequest:
    terrain_root = project_root / "artifacts/goal/m42-s1-terrain-biome"
    terrain_receipt_path = terrain_root / "unreal-biome-terrain-receipt.json"
    terrain = json.loads(terrain_receipt_path.read_text(encoding="utf-8"))
    blender_receipt = json.loads((terrain_root / "blender-terrain-receipt.json").read_text(encoding="utf-8"))
    source_blend = terrain_root / next(item["relative_path"] for item in blender_receipt["artifacts"] if item["kind"] == "blend")
    candidate_file = project_root / "integrations/unreal/ArtFlowBridgeHost/Content" / (terrain["candidate_scene_path"].removeprefix("/Game/") + ".umap")
    if terrain.get("status") != "reconciled" or not source_blend.is_file() or not candidate_file.is_file():
        raise ValueError("simulation cache requires the reconciled terrain candidate")
    core = {
        "schema_id": "artflow-simulation-cache-request/1", "session_id": "scene-session-dc31f6ed0f4e",
        "terrain_receipt_sha256": file_sha256(terrain_receipt_path),
        "source_candidate_scene_path": terrain["candidate_scene_path"],
        "source_candidate_sha256": file_sha256(candidate_file),
        "source_blend_path": source_blend.resolve().as_posix(), "source_blend_sha256": file_sha256(source_blend),
        "capability_id": "blender.cache.wind_veil.v1", "consumer_capability_id": "unreal.geometry_cache.sequence.v1",
        "frame_start": 1, "frame_end": 72, "frame_rate": 24, "mesh_columns": 32, "mesh_rows": 12,
        "amplitude_m": 0.42, "max_cache_bytes": 32 * 1024 * 1024, "output_stem": "AF_WindVeil_Cache",
    }
    identity = canonical_sha256(core)[:12]
    core["sequence_asset_path"] = f"/Game/ArtFlow/Sequences/Generated/LS_AF_WindVeil_{identity}.LS_AF_WindVeil_{identity}"
    provisional = canonical_sha256(core)
    core["request_id"] = f"simulation-cache-{provisional[:16]}"
    core["request_sha256"] = canonical_sha256(core)
    return SimulationCacheRequest.model_validate(core)


def execute_blender_simulation_cache(request: SimulationCacheRequest, *, project_root: Path,
                                     output_dir: Path, blender_executable: Path) -> BlenderSimulationCacheReceipt:
    output_dir.mkdir(parents=True, exist_ok=True)
    if file_sha256(Path(request.source_blend_path)) != request.source_blend_sha256:
        raise ValueError("simulation source blend identity drifted")
    request_path = output_dir / "simulation-cache-request.json"
    request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
    subprocess.run([str(blender_executable), "--background", "--factory-startup", "--python",
                    str(project_root / "integrations/blender/author_wind_veil_cache.py"), "--",
                    str(request_path), str(output_dir)], check=True, cwd=project_root, timeout=360)
    receipt = BlenderSimulationCacheReceipt.model_validate_json((output_dir / "blender-simulation-cache-receipt.json").read_text(encoding="utf-8"))
    if receipt.request_sha256 != request.request_sha256:
        raise ValueError("simulation receipt belongs to another request")
    for artifact in receipt.artifacts:
        path = output_dir / artifact.relative_path
        if file_sha256(path) != artifact.sha256:
            raise ValueError(f"simulation artifact identity mismatch: {artifact.kind}")
        if artifact.kind == "alembic" and artifact.size_bytes > request.max_cache_bytes:
            raise ValueError("Alembic cache exceeds the registered budget")
    return receipt
