import os
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_mcp_config() -> tuple[Path, Dict[str, Any]]:
    """Load MCP config from TOML file specified by MCP_CONFIG_FILE."""
    path = Path(os.getenv("MCP_CONFIG_FILE", "config/mcp.toml"))
    data: Dict[str, Any] = tomllib.loads(path.read_text())
    return path, data["mcp"]


def _server_specs_from_config(config: Dict[str, Any]) -> List[Tuple[str, Any]]:
    """
    Parse servers from config.

    Supported shapes:
    - Shorthand list entries (passed directly to `Client(...)`):
        [[mcp.servers]]
        name = "server_name"
        url = "https://example.com/mcp"  # or "./server.py"

    - Full server config entries (wrapped as MCPConfig and passed to `Client(...)`):
        [[mcp.servers]]
        name = "server_name"
        transport = "http"
        url = "https://example.com/mcp"
        headers = { Authorization = "Bearer ..." }
    """
    servers = config.get("servers")
    if not servers:
        return []
    if not isinstance(servers, list):
        raise TypeError("mcp.servers must be a list (TOML array of tables)")

    specs: List[Tuple[str, Any]] = []
    for item in servers:
        if not isinstance(item, dict):
            raise TypeError(f"mcp.servers entries must be objects, got {type(item).__name__}")

        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("mcp.servers entry missing non-empty 'name'")

        server_def = dict(item)
        server_def.pop("name", None)

        if set(server_def.keys()) == {"url"}:
            specs.append((name, server_def["url"]))
            continue

        specs.append((name, {"mcpServers": {name: server_def}}))

    return specs
