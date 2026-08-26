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
    args = parser.parse_args()
    result = verify_release_archive(args.archive.resolve())
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    if result.status != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
