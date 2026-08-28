from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from artflow_agent.image_to_3d import (
    ImageTo3DGenerationReceipt,
    ImageTo3DGenerationRequest,
    MeshAdmissionPolicy,
    inspect_glb,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    root = args.evidence_dir.resolve()
    request = ImageTo3DGenerationRequest.model_validate_json(
        (root / "generation-request.json").read_text(encoding="utf-8")
    )
    generation = ImageTo3DGenerationReceipt.model_validate_json(
        (root / "generation-receipt.json").read_text(encoding="utf-8")
    )
    policy = MeshAdmissionPolicy()
    receipt = inspect_glb(
        root / "altar-triposr.glb",
        request,
        generation,
        policy,
        inspected_at=datetime.now(UTC),
    )
    (root / "glb-inspection.json").write_text(
        receipt.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (root / "mesh-admission-policy.json").write_text(
        policy.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(receipt.model_dump_json(indent=2))
    return 0 if receipt.status == "admitted" else 2


if __name__ == "__main__":
    raise SystemExit(main())
