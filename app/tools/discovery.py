import logging
from typing import Any, List, Tuple

from .clients import _get_client
from .registry import AgentTool, FastMCPTool

logger = logging.getLogger(__name__)


def _discover_tools_from_client(
    client: Any,
    *,
    prefix: str,
    make_tool: Any,
) -> List[AgentTool]:
    discovered: List[AgentTool] = []
    tools = client.list_tools()
    for tool in tools:
        name = getattr(tool, "name", None)
        if not name:
            raise ValueError(f"MCP tool missing name: {tool}")

        full_name = f"{prefix}{name}"
        description = getattr(tool, "description", "") or ""
        input_schema = getattr(tool, "inputSchema", None)
        parameters = input_schema or {"type": "object", "additionalProperties": True}

        discovered.append(make_tool(full_name, description, parameters))
    return discovered


def _discover_fastmcp_tools(servers: List[Tuple[str, Any]]) -> List[AgentTool]:
    if not servers:
        return []
    discovered: List[AgentTool] = []

    for server_name, client_spec in servers:
        client = _get_client(client_spec)

        discovered.extend(
            _discover_tools_from_client(
                client,
                prefix="",
                make_tool=lambda name, description, params, client_spec=client_spec, server_name=server_name: FastMCPTool(
                    name=name,
                    description=description or "FastMCP tool",
                    parameters=params,
                    client_spec=client_spec,
                    source=f"mcp:{server_name}",
                ),
            )
        )

    return discovered
