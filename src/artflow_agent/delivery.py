from __future__ import annotations

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from .run_store import RunStateError, RunStore


def package_run(store: RunStore, run_id: str, output_path: Path) -> Path:
    state = store.load(run_id)
    if state.status != "completed":
        raise RunStateError("Only a human-selected completed run can be packaged")
    run_root = (store.root / run_id).resolve()
    selected = next(
        (
            candidate
            for candidate in state.candidates
            if candidate.candidate_id == state.selected_candidate_id
        ),
        None,
    )
    selected_path = Path(selected.image_path).resolve() if selected is not None else None
    if (
        selected_path is None
        or not selected_path.is_relative_to(run_root)
        or not selected_path.is_file()
    ):
        raise RunStateError("Selected candidate must be a recorded artifact inside the run")
    files = sorted(path for path in run_root.rglob("*") if path.is_file())
    manifest = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "selected_candidate_id": state.selected_candidate_id,
        "files": [
            {
                "path": path.relative_to(run_root).as_posix(),
                "sha256": _sha256(path),
                "size": path.stat().st_size,
            }
            for path in files
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".part")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(run_root).as_posix())
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    temporary.replace(output_path)
    return output_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
