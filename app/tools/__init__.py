"""Tool registry and MCP integration package.

Public surface is re-exported here so callers can keep using
`from app.tools import ToolRegistry, build_default_registry`, etc.
"""

from .config import _load_mcp_config
from .discovery import (
    _discover_fastmcp_http_servers_from_config,
    _discover_fastmcp_stdio_servers_from_config,
    _load_fastmcp_stdio_tools_from_config,
)
from .registry import AgentTool, FastMCPHttpTool, FastMCPStdioTool, ToolRegistry


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    config = _load_mcp_config()

    for stdio_server_tool in _discover_fastmcp_stdio_servers_from_config(config):
        registry.register(stdio_server_tool)

    for http_server_tool in _discover_fastmcp_http_servers_from_config(config):
        registry.register(http_server_tool)

    for stdio_tool in _load_fastmcp_stdio_tools_from_config(config):
        registry.register(stdio_tool)

    return registry


__all__ = [
    "AgentTool",
    "FastMCPStdioTool",
    "FastMCPHttpTool",
    "ToolRegistry",
    "build_default_registry",
]
