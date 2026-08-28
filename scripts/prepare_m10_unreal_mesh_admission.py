from __future__ import annotations

import argparse
from pathlib import Path

from artflow_agent.image_to_3d import (
    GLBInspectionReceipt,
    ImageTo3DGenerationReceipt,
    UnrealMeshAdmissionRequest,
    file_sha256,
)
from artflow_agent.scene_lifecycle import canonical_sha256


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    root = args.evidence_dir.resolve()
    repo = Path(__file__).resolve().parents[1]
    generation = ImageTo3DGenerationReceipt.model_validate_json(
        (root / "generation-receipt.json").read_text(encoding="utf-8")
    )
    inspection = GLBInspectionReceipt.model_validate_json(
        (root / "glb-inspection.json").read_text(encoding="utf-8")
    )
    if inspection.status != "admitted":
        parser.error("only a pre-import admitted GLB can enter Unreal quarantine")
    source_map = repo / "integrations/unreal/ArtFlowBridgeHost/Content/ArtFlowDemo.umap"
    payload = {
        "request_id": f"m10-unreal-{inspection.candidate_sha256[:20]}",
        "generation_receipt_sha256": generation.receipt_sha256,
        "inspection_receipt_sha256": inspection.receipt_sha256,
        "candidate_relative_path": (
            "artifacts/goal/m10-s2-image-to-3d/altar-triposr.glb"
        ),
        "candidate_sha256": inspection.candidate_sha256,
        "destination_root": f"/Game/ArtFlow/Generated/m10_{inspection.candidate_sha256[:12]}",
        "asset_name": "SM_AF_GeneratedAltar",
        "target_longest_extent_cm": 180.0,
        "unreal_uniform_scale": inspection.unreal_uniform_scale,
        "material_strategy": inspection.material_strategy,
        "normals_strategy": inspection.normals_strategy,
        "collision_strategy": inspection.collision_strategy,
        "authority_scope": "project_local_unreal_fixture",
        "source_scene_sha256": file_sha256(source_map),
    }
    payload["request_sha256"] = canonical_sha256(
        UnrealMeshAdmissionRequest.model_construct(
            **payload, request_sha256="0" * 64
        ).model_dump(mode="json", exclude={"request_sha256"})
    )
    request = UnrealMeshAdmissionRequest(**payload)
    (root / "unreal-admission-request.json").write_text(
        request.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(request.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
