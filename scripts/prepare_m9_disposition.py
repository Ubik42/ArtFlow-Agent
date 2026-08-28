from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from artflow_agent.scene_lifecycle import (
    LightingPatchReceipt,
    SceneDeltaEvaluation,
    VerifiedDispositionRequest,
    canonical_sha256,
)


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--correction-receipt", type=Path, required=True)
    parser.add_argument("--candidate-map", type=Path, required=True)
    parser.add_argument("--base-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evaluation = SceneDeltaEvaluation.model_validate_json(args.evaluation.read_text(encoding="utf-8"))
    correction = LightingPatchReceipt.model_validate_json(
        args.correction_receipt.read_text(encoding="utf-8")
    )
    base = json.loads(args.base_receipt.read_text(encoding="utf-8"))
    if evaluation.status != "verified" or evaluation.failed_domains:
        raise ValueError("only an independently verified candidate can be published")
    candidate_sha = file_sha(args.candidate_map)
    identity = canonical_sha256(
        {
            "evaluation": evaluation.evaluation_sha256,
            "correction": correction.receipt_sha256,
            "candidate": candidate_sha,
        }
    )
    payload = {
        "schema_id": "verified-scene-disposition-request/1",
        "disposition_id": f"m9-disposition-{identity[:20]}",
        "disposition": "published",
        "evaluation_sha256": evaluation.evaluation_sha256,
        "correction_receipt_sha256": correction.receipt_sha256,
        "candidate_scene_path": correction.candidate_scene_path,
        "candidate_scene_sha256": candidate_sha,
        "published_scene_path": f"/Game/ArtFlow/Published/AF_M9_{identity[:12]}",
        "source_scene_sha256": base["source_scene_sha256_after"],
        "idempotency_key": f"m9:disposition:{identity[:32]}",
    }
    payload["request_sha256"] = canonical_sha256(payload)
    request = VerifiedDispositionRequest.model_validate(payload)
    args.output.write_text(
        json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
