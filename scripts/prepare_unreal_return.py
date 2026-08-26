from __future__ import annotations

import hashlib
import json
from pathlib import Path

from artflow_agent.provenance import (
    EvidenceBinding,
    UnrealReturnRequest,
    canonical_sha256,
    sha256_file,
)

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "local-artflow-ue-7e66ea0f40432643e4ac63a8f39f98c6-130c94284deb"
REVISION_ROOT = ROOT / "artifacts" / "goal" / "m4-s3-bounded-revision"
OUTPUT_ROOT = ROOT / "artifacts" / "goal" / "m6-s1-unreal-return"


def relative_binding(role: str, path: Path, media_type: str) -> EvidenceBinding:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise RuntimeError(f"Evidence escaped repository: {role}")
    return EvidenceBinding(
        role=role,
        path=resolved.relative_to(ROOT).as_posix(),
        sha256=sha256_file(resolved),
        media_type=media_type,
    )


def main() -> None:
    revision_result_path = REVISION_ROOT / "bounded-revision-result.json"
    revision_result = json.loads(revision_result_path.read_text(encoding="utf-8"))
    source = REVISION_ROOT / revision_result["composite_artifact_path"]
    expected = revision_result["composite_artifact_sha256"]
    if sha256_file(source) != expected:
        raise RuntimeError("Verified revision artifact no longer matches its receipt")

    evidence_paths = {
        "adoption_decision_sha256": REVISION_ROOT / "adoption-decision.json",
        "tribunal_sha256": ROOT / "artifacts/goal/m4-s1-tribunal/tribunal-report.json",
        "multimodal_tribunal_sha256": ROOT
        / "artifacts/goal/m4-s2-negative-control/multimodal-tribunal-report.json",
        "bounded_revision_request_sha256": REVISION_ROOT / "revision-request.json",
        "bounded_revision_result_sha256": revision_result_path,
    }
    seed = hashlib.sha256(
        (RUN_ID + expected + revision_result["revision_id"]).encode()
    ).hexdigest()[:20]
    payload = {
        "schema_id": "artflow-unreal-return-request/1",
        "import_id": f"return-{seed}",
        "run_id": RUN_ID,
        "source": relative_binding("verified_revision", source, "image/png").model_dump(
            mode="json"
        ),
        "destination_asset_path": f"/Game/ArtFlow/Returns/T_ArtFlow_{seed}",
        "destination_scene_path": "/Game/ArtFlowDemo",
        "source_scene_package_sha256": json.loads(
            (REVISION_ROOT / "revision-request.json").read_text(encoding="utf-8")
        )["scene_package_sha256"],
        **{name: sha256_file(path) for name, path in evidence_paths.items()},
        "operation": "import_art_direction_texture_and_bind_scene",
        "authority_scope": "project_local_unreal_fixture",
        "request_sha256": "0" * 64,
    }
    payload["request_sha256"] = canonical_sha256(payload, "request_sha256")
    request = UnrealReturnRequest.model_validate(payload)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT_ROOT / "unreal-return-request.json"
    encoded = json.dumps(request.model_dump(mode="json"), indent=2) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") != encoded:
        raise RuntimeError("A different return request already occupies the import identity")
    target.write_text(encoded, encoding="utf-8")
    print(f"REQUEST={target} IMPORT={request.import_id} SHA256={request.request_sha256}")


if __name__ == "__main__":
    main()
