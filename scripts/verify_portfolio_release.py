from __future__ import annotations

import argparse
import json
from pathlib import Path

from artflow_agent.portfolio_release import verify_release_archive


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Independently verify an ArtFlow local portfolio release"
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for the machine-readable verification receipt",
    )
    args = parser.parse_args()
    result = verify_release_archive(args.archive.resolve())
    serialized = json.dumps(result.model_dump(mode="json"), indent=2)
    print(serialized)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    if result.status != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
