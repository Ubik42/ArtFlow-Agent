import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from artflow_agent.scene_packages import ScenePackageArchive, ScenePackageImportError


def _archive(tmp_path: Path, *, corrupt: str | None = None, unsafe_entry: bool = False) -> Path:
    root = Path(__file__).parents[1]
    manifest = json.loads(
        (root / "examples" / "scene-constraint-package.example.json").read_text(encoding="utf-8")
    )
    artifacts = {
        "passes/beauty.png": b"beauty",
        "passes/depth.exr": b"depth",
        "passes/world-normal.exr": b"world-normal",
        "passes/object-id.png": b"object-id",
    }
    for item in manifest["passes"]:
        item["artifact"]["sha256"] = hashlib.sha256(
            artifacts[item["artifact"]["path"]]
        ).hexdigest()

    path = tmp_path / "scene-package.zip"
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("scene-package.json", json.dumps(manifest))
        for name, content in artifacts.items():
            archive.writestr(name, b"corrupt" if name == corrupt else content)
        if unsafe_entry:
            archive.writestr("../outside.txt", b"escape")
    return path


def test_atomic_scene_package_is_verified_without_extraction(tmp_path) -> None:
    preview = ScenePackageArchive().inspect(_archive(tmp_path))

    assert preview.package.package_id == "coastal-ruins-ue-capture-001"
    assert {item.path for item in preview.artifacts} == {
        "passes/beauty.png",
        "passes/depth.exr",
        "passes/world-normal.exr",
        "passes/object-id.png",
    }
    assert preview.protected_region_ids == ["main-ruin"]
    assert preview.editable_region_ids == ["arch-repair"]
    assert not (tmp_path / "passes").exists()


def test_scene_package_rejects_hash_mismatch_and_zip_traversal(tmp_path) -> None:
    with pytest.raises(ScenePackageImportError, match="hash mismatch"):
        ScenePackageArchive().inspect(_archive(tmp_path, corrupt="passes/depth.exr"))

    with pytest.raises(ScenePackageImportError, match="Unsafe archive entry"):
        ScenePackageArchive().inspect(_archive(tmp_path, unsafe_entry=True))
