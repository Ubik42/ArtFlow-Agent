from __future__ import annotations

from artflow_agent.mcp_facade import default_mcp_server

if __name__ == "__main__":
    default_mcp_server().run(transport="stdio")
