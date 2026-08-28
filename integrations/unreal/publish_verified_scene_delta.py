from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import unreal


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(f"ArtFlow verified publish failed closed: {message}")


repo_root = Path(os.environ["ARTFLOW_REPO_ROOT"]).resolve()
request_path = Path(os.environ["ARTFLOW_M9_DISPOSITION_REQUEST"]).resolve()
result_path = Path(os.environ["ARTFLOW_M9_DISPOSITION_RESULT"]).resolve()
if not request_path.is_relative_to(repo_root) or not result_path.is_relative_to(repo_root):
    fail("request or result escaped the repository")
request = json.loads(request_path.read_text(encoding="utf-8"))
if request.get("schema_id") != "verified-scene-disposition-request/1":
    fail("unsupported request schema")
unsigned = dict(request)
request_sha = unsigned.pop("request_sha256", None)
if canonical_sha256(unsigned) != request_sha:
    fail("disposition request fingerprint mismatch")
if request.get("disposition") != "published":
    fail("this executor only publishes; discard uses a separate destructive path")
if request["candidate_scene_path"] != "/Game/ArtFlow/Staging/AF_cb2176a7a45bbad1":
    fail("unexpected candidate namespace")
if not request["published_scene_path"].startswith("/Game/ArtFlow/Published/AF_M9_"):
    fail("published path escaped the content-addressed M9 namespace")

project_root = Path(unreal.Paths.project_dir()).resolve()
source_file = project_root / "Content" / "ArtFlowDemo.umap"
candidate_file = project_root / "Content" / "ArtFlow" / "Staging" / "AF_cb2176a7a45bbad1.umap"
published_file = project_root / "Content" / Path(request["published_scene_path"].removeprefix("/Game/") + ".umap")
source_before = file_sha(source_file)
if source_before != request["source_scene_sha256"]:
    fail("source scene fingerprint is stale")
if file_sha(candidate_file) != request["candidate_scene_sha256"]:
    fail("candidate scene changed after verified evaluation")

metadata_key = "ArtFlow.DispositionRequestSha256"
reconciled = unreal.EditorAssetLibrary.does_asset_exist(request["published_scene_path"])
if reconciled:
    published = unreal.EditorAssetLibrary.load_asset(request["published_scene_path"])
    if published is None or unreal.EditorAssetLibrary.get_metadata_tag(published, metadata_key) != request_sha:
        fail("published path exists but does not belong to this disposition request")
else:
    published = unreal.EditorAssetLibrary.duplicate_asset(
        request["candidate_scene_path"], request["published_scene_path"]
    )
    if published is None:
        fail("candidate scene could not be duplicated into the published namespace")
    unreal.EditorAssetLibrary.set_metadata_tag(published, metadata_key, request_sha)
    unreal.EditorAssetLibrary.set_metadata_tag(
        published, "ArtFlow.EvaluationSha256", request["evaluation_sha256"]
    )
    if not unreal.EditorAssetLibrary.save_asset(request["published_scene_path"], only_if_is_dirty=False):
        fail("published scene could not be saved")
if not published_file.is_file():
    fail("published map file is missing after save")
source_after = file_sha(source_file)
if source_after != source_before:
    fail("publish changed the source scene")

result = {
    "schema_id": "verified-scene-disposition-receipt/1",
    "disposition_id": request["disposition_id"],
    "disposition": "published",
    "evaluation_sha256": request["evaluation_sha256"],
    "correction_receipt_sha256": request["correction_receipt_sha256"],
    "candidate_scene_path": request["candidate_scene_path"],
    "published_scene_path": request["published_scene_path"],
    "published_scene_sha256": file_sha(published_file),
    "source_scene_sha256_before": source_before,
    "source_scene_sha256_after": source_after,
    "duplicate_side_effect_count": 0,
    "completed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
result["receipt_sha256"] = canonical_sha256(result)
result_path.parent.mkdir(parents=True, exist_ok=True)
temporary = result_path.with_suffix(result_path.suffix + ".tmp")
temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
temporary.replace(result_path)
unreal.log(
    f"ARTFLOW_M9_DISPOSITION status={'reconciled' if reconciled else 'published'} "
    f"path={request['published_scene_path']}"
)
