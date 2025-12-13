"""Tool registry and MCP integration package.

Public surface is re-exported here so callers can keep using
`from app.tools import ToolRegistry, build_default_registry`, etc.
"""

from .config import _load_mcp_config, _server_specs_from_config
from .discovery import _discover_fastmcp_tools
from .registry import AgentTool, FastMCPTool, ToolRegistry


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    _, config = _load_mcp_config()
    servers = _server_specs_from_config(config)
    for tool in _discover_fastmcp_tools(servers):
        registry.register(tool)

    return registry


__all__ = [
    "AgentTool",
    "FastMCPTool",
    "ToolRegistry",
    "build_default_registry",
]
