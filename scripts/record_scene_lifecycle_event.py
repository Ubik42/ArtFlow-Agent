from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.scene_lifecycle import SceneLifecycleLedger


def main() -> int:
    parser = argparse.ArgumentParser(description="Append one idempotent ArtFlow scene lifecycle event.")
    parser.add_argument("database", type=Path)
    parser.add_argument("event_type")
    parser.add_argument("idempotency_key")
    parser.add_argument("--payload", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    event = SceneLifecycleLedger(args.database).append(
        args.event_type, args.idempotency_key, payload
    )
    print(event.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
