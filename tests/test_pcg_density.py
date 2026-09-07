import hashlib
import json
from pathlib import Path

from PIL import Image

from artflow_agent.pcg_density import compile_pcg_density_request


def test_density_request_binds_scene_kit_and_fixed_consumers(tmp_path: Path) -> None:
    depth = tmp_path / "depth.png"
    Image.new("L", (640, 360), 127).save(depth)
    manifest = tmp_path / "manifest.json"
    manifest.write_text("{}")
    manifest_sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    receipt = tmp_path / "receipt.json"
    receipt.write_text(json.dumps({"receipt_sha256": "a" * 64, "artifacts": [{"kind": "manifest", "sha256": manifest_sha}]}))
    request = compile_pcg_density_request(
        session_id="scene-session-dc31f6ed0f4e", scene_package_sha256="b" * 64,
        depth_path=depth, kit_receipt_path=receipt, kit_manifest_path=manifest,
    )
    assert request.comfy_capability_id == "comfy.pcg_density.depth_exclusion.v1"
    assert request.unreal_consumer_capability_id == "unreal.pcg.native_density_kit.v1"
