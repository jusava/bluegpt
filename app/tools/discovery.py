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


def _discover_tools_from_client(
    client: Any,
    *,
    prefix: str,
    make_tool: Any,
) -> List[AgentTool]:
    discovered: List[AgentTool] = []
    tools = client.list_tools()
    for tool_def in tools:
        base_name = _tfield(tool_def, "name")
        if not base_name:
            raise ValueError(f"MCP tool missing name: {tool_def}")
        name = f"{prefix}{base_name}"
        description = _tfield(tool_def, "description") or ""
        params = (
            _tfield(tool_def, "input_schema")
            or _tfield(tool_def, "parameters")
            or {"type": "object", "additionalProperties": True}
        )
        discovered.append(make_tool(name, description, params))
    return discovered


def _discover_fastmcp_stdio_servers_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    servers = config.get("stdio_servers", [])
    if not servers:
        return []

    discovered: List[AgentTool] = []

    def handle_one(item: Dict[str, Any]) -> None:
        command = item["command"]
        args = item.get("args") or []
        env = item.get("env")
        cwd = item.get("cwd")
        client = _get_process_client(command, args, env, cwd)
        discovered.extend(
            _discover_tools_from_client(
                client,
                prefix="",
                make_tool=lambda name, description, params: FastMCPStdioTool(
                    name=name,
                    description=description or "FastMCP stdio tool",
                    parameters=params,
                    command=command,
                    args=args,
                    env=env,
                    cwd=cwd,
                ),
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
        url = item["url"]
        headers = item.get("headers")
        auth = item.get("auth")
        sse_read_timeout = item.get("sse_read_timeout")
        client = _get_http_client(url, headers, auth, sse_read_timeout)
        discovered.extend(
            _discover_tools_from_client(
                client,
                prefix="",
                make_tool=lambda name, description, params: FastMCPHttpTool(
                    name=name,
                    description=description or "FastMCP http tool",
                    parameters=params,
                    url=url,
                    headers=headers,
                    auth=auth,
                    sse_read_timeout=sse_read_timeout,
                ),
            )
        )

    for item in servers:
        handle_one(item)
    return discovered


def _load_fastmcp_stdio_tools_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    return []
