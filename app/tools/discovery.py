import logging
from typing import Any, Dict, List

from .clients import _get_http_client, _get_process_client
from .registry import AgentTool, FastMCPHttpTool, FastMCPStdioTool

logger = logging.getLogger(__name__)


def _camel(s: str) -> str:
    parts = s.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


def _tfield(tool_def: Any, attr: str) -> Any:
    if hasattr(tool_def, attr):
        return getattr(tool_def, attr)
    camel_attr = _camel(attr)
    if hasattr(tool_def, camel_attr):
        return getattr(tool_def, camel_attr)
    if isinstance(tool_def, dict):
        return tool_def.get(attr) or tool_def.get(camel_attr)
    return None


def _discover_fastmcp_stdio_servers_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    servers = config.get("stdio_servers", [])
    if not servers:
        return []

    discovered: List[AgentTool] = []

    def handle_one(item: Dict[str, Any]) -> None:
        client = _get_process_client(item["command"], item.get("args") or [], item.get("env"), item.get("cwd"))
        prefix = ""
        tools = client.list_tools()
        for tool_def in tools:
            base_name = _tfield(tool_def, "name")
            if not base_name:
                raise ValueError(f"MCP stdio tool missing name: {tool_def}")
            name = f"{prefix}{base_name}"
            description = _tfield(tool_def, "description") or ""
            params = (
                _tfield(tool_def, "input_schema")
                or _tfield(tool_def, "parameters")
                or {"type": "object", "additionalProperties": True}
            )
            discovered.append(
                FastMCPStdioTool(
                    name=name,
                    description=description or "FastMCP stdio tool",
                    parameters=params,
                    command=item["command"],
                    args=item.get("args") or [],
                    env=item.get("env"),
                    cwd=item.get("cwd"),
                )
            )

    for item in servers:
        handle_one(item)
    return discovered


def _discover_fastmcp_http_servers_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    servers = config.get("http_servers", [])
    if not servers:
        return []

    discovered: List[AgentTool] = []

    def handle_one(item: Dict[str, Any]) -> None:
        url = item.get("url")
        if not url:
            raise ValueError(f"MCP http server missing url: {item}")
        client = _get_http_client(url, item.get("headers"), item.get("auth"), item.get("sse_read_timeout"))
        prefix = ""
        tools = client.list_tools()
        for tool_def in tools:
            base_name = _tfield(tool_def, "name")
            if not base_name:
                raise ValueError(f"MCP http tool missing name: {tool_def}")
            name = f"{prefix}{base_name}"
            description = _tfield(tool_def, "description") or ""
            params = (
                _tfield(tool_def, "input_schema")
                or _tfield(tool_def, "parameters")
                or {"type": "object", "additionalProperties": True}
            )
            discovered.append(
                FastMCPHttpTool(
                    name=name,
                    description=description or "FastMCP http tool",
                    parameters=params,
                    url=url,
                    headers=item.get("headers"),
                    auth=item.get("auth"),
                    sse_read_timeout=item.get("sse_read_timeout"),
                )
            )

    for item in servers:
        handle_one(item)
    return discovered


def _load_fastmcp_stdio_tools_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    return []

