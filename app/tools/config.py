import json
import os
import tomllib
from pathlib import Path
from typing import Any, Dict, List


def _load_mcp_config() -> Dict[str, Any]:
    """Load MCP config from TOML or standard MCP JSON file (via MCP_CONFIG_FILE)."""
    path = Path(os.getenv("MCP_CONFIG_FILE", "config/mcp.toml"))
    text = path.read_text()
    if path.suffix.lower() == ".json":
        return json.loads(text)
    return tomllib.loads(text)


def _normalize_mcp_config(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize TOML-style or standard MCP JSON config into {stdio_servers, http_servers}."""
    config: Dict[str, Any] = raw.get("mcp") if isinstance(raw.get("mcp"), dict) else raw

    stdio_servers: List[Dict[str, Any]] = list(config.get("stdio_servers") or [])
    http_servers: List[Dict[str, Any]] = list(config.get("http_servers") or [])

    mcp_servers = config.get("mcpServers") or config.get("mcp_servers")
    if isinstance(mcp_servers, dict):
        for name, server in mcp_servers.items():
            if not isinstance(server, dict):
                continue
            if server.get("url"):
                http_servers.append(
                    {
                        "name": name,
                        "url": server["url"],
                        "headers": server.get("headers"),
                        "auth": server.get("auth") or server.get("authorization_token"),
                        "sse_read_timeout": server.get("sse_read_timeout"),
                    }
                )
            elif server.get("command"):
                stdio_servers.append(
                    {
                        "name": name,
                        "command": server["command"],
                        "args": server.get("args") or [],
                        "env": server.get("env"),
                        "cwd": server.get("cwd"),
                    }
                )

    return {"stdio_servers": stdio_servers, "http_servers": http_servers}

