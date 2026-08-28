from __future__ import annotations

import argparse
import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import httpx

from artflow_agent.pbr import PBRWorkflowCompiler, capture_capability_snapshot

ROOT = Path(__file__).resolve().parents[1]


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Capture a real bounded ComfyUI PBR capability snapshot.")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8190")
    parser.add_argument("--production-nodes", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    compiler = PBRWorkflowCompiler(
        ROOT / "recipes/pbr-material-v1.template.json",
        ROOT / "recipes/pbr-material-v1.workflow.json",
    )
    with httpx.Client(base_url=args.endpoint, timeout=20) as client:
        stats_response = client.get("/system_stats")
        object_response = client.get("/object_info")
        stats_response.raise_for_status()
        object_response.raise_for_status()
        stats = stats_response.json()
        object_info = object_response.json()
    commit = subprocess.check_output(
        ["git", "-C", str(args.production_nodes), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    license_path = args.production_nodes / "LICENSE"
    snapshot = capture_capability_snapshot(
        endpoint=args.endpoint,
        system_stats=stats,
        object_info=object_info,
        required_nodes=compiler.template.required_nodes,
        production_nodes_commit=commit,
        production_nodes_license_sha256=hashlib.sha256(license_path.read_bytes()).hexdigest(),
        captured_at=datetime.now(UTC),
    )
    atomic_write(args.output, snapshot.model_dump_json(indent=2) + "\n")
    print(snapshot.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
