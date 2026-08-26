from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from artflow_agent.web_api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve one persisted ArtFlow Agent event store")
    parser.add_argument("root", type=Path)
    parser.add_argument("--port", type=int, default=8792)
    args = parser.parse_args()
    root = args.root.resolve()
    uvicorn.run(
        create_app(runs_dir=root, agent_database=root / "agent-events.sqlite3"),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
