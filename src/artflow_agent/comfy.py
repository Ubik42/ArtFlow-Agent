from __future__ import annotations

import httpx

from .domain import EnvironmentSnapshot


def inspect_environment(comfy_url: str, timeout_seconds: float = 3.0) -> EnvironmentSnapshot:
    base_url = comfy_url.rstrip("/")
    try:
        response = httpx.get(f"{base_url}/system_stats", timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return EnvironmentSnapshot(comfy_url=base_url, reachable=False)

    devices = payload.get("devices") or []
    vram_bytes = devices[0].get("vram_total") if devices else None
    return EnvironmentSnapshot(
        comfy_url=base_url,
        reachable=True,
        vram_mb=int(vram_bytes / 1024 / 1024) if isinstance(vram_bytes, (int, float)) else None,
    )

