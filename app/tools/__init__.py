"""Tool registry and MCP integration package.

Public surface is re-exported here so callers can keep using
`from app.tools import ToolRegistry, build_default_registry`, etc.
"""

from .mcp import discover_tools, load_mcp_config, server_specs_from_config
from .registry import AgentTool, FastMCPTool, ToolRegistry


async def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    config = load_mcp_config()
    servers = server_specs_from_config(config)
    for tool in await discover_tools(servers):
        registry.register(tool)

    return registry


__all__ = [
    "AgentTool",
    "FastMCPTool",
    "ToolRegistry",
    "build_default_registry",
]
