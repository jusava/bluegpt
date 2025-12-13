import os
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .clients import get_client
from .registry import AgentTool, FastMCPTool


def load_mcp_config() -> Dict[str, Any]:
    path = Path(os.getenv("MCP_CONFIG_FILE", "config/mcp.toml"))
    data: Dict[str, Any] = tomllib.loads(path.read_text())
    return data.get("mcp") or {}


def server_specs_from_config(config: Dict[str, Any]) -> List[Tuple[str, Any]]:
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


async def discover_tools(servers: List[Tuple[str, Any]]) -> List[AgentTool]:
    if not servers:
        return []

    discovered: List[AgentTool] = []
    for server_name, client_spec in servers:
        client = get_client(client_spec)
        async with client:
            tools = await client.list_tools()

        for tool in tools:
            name = getattr(tool, "name", None)
            if not name:
                raise ValueError(f"MCP tool missing name: {tool}")

            discovered.append(
                FastMCPTool(
                    name=name,
                    description=getattr(tool, "description", "") or "",
                    parameters=getattr(tool, "inputSchema", None)
                    or {"type": "object", "additionalProperties": True},
                    client_spec=client_spec,
                    source=f"mcp:{server_name}",
                )
            )

    return discovered

