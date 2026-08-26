from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.agent_runtime import AgentEventStore
from artflow_agent.codex_image_ingress import import_negative_control


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Normalize a Codex built-in attractive-invalid control."
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--beauty-sha256", required=True)
    args = parser.parse_args()
    database = args.database.resolve()
    record = import_negative_control(
        AgentEventStore(database),
        args.run_id,
        args.image.resolve(),
        args.prompt.read_text(encoding="utf-8"),
        artifact_root=database.parent / ".agent-artifacts" / "provider-outputs",
        expected_archive_sha256=args.archive_sha256,
        expected_beauty_sha256=args.beauty_sha256,
    )
    print(json.dumps(record.model_dump(mode="json"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
