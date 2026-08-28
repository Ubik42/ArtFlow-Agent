from __future__ import annotations

import argparse
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from gradio_client import Client, handle_file

from artflow_agent.image_to_3d import (
    ImageTo3DGenerationReceipt,
    ImageTo3DGenerationRequest,
    file_sha256,
)
from artflow_agent.scene_lifecycle import canonical_sha256

PROVIDER_REVISION = "f84354eb350eb07a108faf33a6bc564d455f9764"
LICENSE_URL = "https://raw.githubusercontent.com/VAST-AI-Research/TripoSR/main/LICENSE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence_dir", type=Path)
    args = parser.parse_args()
    root = args.evidence_dir.resolve()
    source = root / "altar-reference.png"
    license_path = root / "TRIPOSR-LICENSE.txt"
    if not source.is_file() or not license_path.is_file():
        parser.error("project-owned reference and pinned provider license are required")

    source_sha = file_sha256(source)
    request_payload = {
        "request_id": f"m10-mesh-{source_sha[:20]}",
        "source_artifact_id": "m10-ruin-altar-reference",
        "source_image_sha256": source_sha,
        "provider_id": "stabilityai-triposr-space",
        "model_id": "stabilityai/TripoSR",
        "provider_revision": PROVIDER_REVISION,
        "license_spdx": "MIT",
        "license_sha256": file_sha256(license_path),
        "license_source_url": LICENSE_URL,
        "foreground_ratio": 0.85,
        "marching_cubes_resolution": 256,
    }
    request_payload["request_sha256"] = canonical_sha256(
        ImageTo3DGenerationRequest.model_construct(
            **request_payload, request_sha256="0" * 64
        ).model_dump(mode="json", exclude={"request_sha256"})
    )
    request = ImageTo3DGenerationRequest(**request_payload)
    started = time.perf_counter()
    client = Client("stabilityai/TripoSR")
    processed_remote = client.predict(
        handle_file(source), request.remove_background, request.foreground_ratio, api_name="/preprocess"
    )
    _, glb_remote = client.predict(
        handle_file(processed_remote), request.marching_cubes_resolution, api_name="/generate"
    )
    processed = root / "altar-processed.png"
    glb = root / "altar-triposr.glb"
    shutil.copy2(processed_remote, processed)
    shutil.copy2(glb_remote, glb)
    receipt_payload = {
        "request_id": request.request_id,
        "request_sha256": request.request_sha256,
        "provider_id": request.provider_id,
        "model_id": request.model_id,
        "provider_endpoint": "https://stabilityai-triposr.hf.space",
        "processed_image_sha256": file_sha256(processed),
        "glb_sha256": file_sha256(glb),
        "glb_size_bytes": glb.stat().st_size,
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "completed_at": datetime.now(UTC),
    }
    receipt_payload["receipt_sha256"] = canonical_sha256(
        ImageTo3DGenerationReceipt.model_construct(
            **receipt_payload, receipt_sha256="0" * 64
        ).model_dump(mode="json", exclude={"receipt_sha256"})
    )
    receipt = ImageTo3DGenerationReceipt(**receipt_payload)
    (root / "generation-request.json").write_text(
        request.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    (root / "generation-receipt.json").write_text(
        receipt.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(receipt.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
