from __future__ import annotations

import argparse
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from artflow_agent.web_api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="启动 ArtFlow 中文展示界面")
    parser.add_argument("--port", type=int, default=8798)
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="服务就绪后在默认浏览器打开 Scene Lab",
    )
    args = parser.parse_args()

    root = (
        Path(__file__).resolve().parents[1]
        / "artifacts"
        / "goal"
        / "m3-s11-local-run"
    )
    if not (root / "agent-events.sqlite3").is_file():
        raise SystemExit("展示数据缺失，请确认仓库中的演示制品已完整下载。")

    if args.open_browser:
        url = f"http://127.0.0.1:{args.port}"

        def open_when_ready() -> None:
            for _ in range(40):
                try:
                    with urllib.request.urlopen(f"{url}/api/health", timeout=0.25):
                        webbrowser.open(url)
                        return
                except OSError:
                    time.sleep(0.15)

        threading.Thread(target=open_when_ready, daemon=True).start()

    uvicorn.run(
        create_app(runs_dir=root, agent_database=root / "agent-events.sqlite3"),
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
