import asyncio
import json
import logging
import os
import threading
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


ToolHandler = Callable[[Dict[str, Any]], Awaitable[str] | str]


@dataclass
class AgentTool:
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: ToolHandler
    source: str = field(default="local")

    async def __call__(self, arguments: Dict[str, Any]) -> str:
        result = self.handler(arguments)
        if asyncio.iscoroutine(result):
            result = await result
        return str(result)

    def as_openai_tool(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def as_response_tool(self) -> Dict[str, Any]:
        # Responses API expects tool name/description at the top level.
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            # input_schema is the preferred field for the Responses API.
            "input_schema": self.parameters,
        }


class MCPHTTPTool(AgentTool):
    """Adapter for calling a remote MCP server that exposes HTTP tool endpoints."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        endpoint: str,
    ) -> None:
        super().__init__(name=name, description=description, parameters=parameters, handler=self._call_remote)
        self.endpoint = endpoint
        self.source = "mcp-http"

    async def _call_remote(self, arguments: Dict[str, Any]) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self.endpoint, json={"tool": self.name, "arguments": arguments})
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and "result" in payload:
                return json.dumps(payload["result"]) if isinstance(payload["result"], (dict, list)) else str(payload["result"])
            return json.dumps(payload)


class FastMCPStdioTool(AgentTool):
    """Adapter for calling a FastMCP server over stdio."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd

        super().__init__(name=name, description=description, parameters=parameters, handler=self._call_stdio)
        self.source = "mcp-stdio"

    async def _call_stdio(self, arguments: Dict[str, Any]) -> str:
        try:
            from fastmcp import Client
            from fastmcp.client.transports import StdioTransport
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("fastmcp is not installed. Please add fastmcp to your environment.") from exc

        transport = StdioTransport(command=self.command, args=self.args, env=self.env, cwd=self.cwd)
        client = Client(transport)
        async with client:
            result = await client.call_tool(self.name, arguments or {})
        if isinstance(result, (dict, list)):
            return json.dumps(result)
        return str(result)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool
        logger.debug("Registered tool %s (source=%s)", tool.name, tool.source)

    def list_for_openai(self) -> List[Dict[str, Any]]:
        return [tool.as_openai_tool() for tool in self._tools.values()]

    def list_for_responses(self) -> List[Dict[str, Any]]:
        return [tool.as_response_tool() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered")
        return await self._tools[name](arguments)

    def summary(self) -> List[Dict[str, str]]:
        return [
            {"name": tool.name, "description": tool.description, "source": tool.source}
            for tool in self._tools.values()
        ]


def _build_time_tool() -> AgentTool:
    def current_time(_: Dict[str, Any]) -> str:
        return datetime.now(timezone.utc).isoformat()

    return AgentTool(
        name="utc_time",
        description="Returns the current UTC time in ISO-8601 format.",
        parameters={"type": "object", "properties": {}, "additionalProperties": False},
        handler=current_time,
    )


def _load_mcp_tools_from_env() -> List[AgentTool]:
    """Load MCP HTTP tools from MCP_HTTP_TOOLS env var if provided.

    Expected format:
    [
      {"name": "docs_search", "description": "Search docs", "endpoint": "http://localhost:9000/tools/docs_search",
       "parameters": {...}}
    ]
    """
    raw = os.getenv("MCP_HTTP_TOOLS")
    if not raw:
        return []

    try:
        definitions = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("MCP_HTTP_TOOLS is not valid JSON; skipping MCP tool registration.")
        return []

    tools: List[AgentTool] = []
    for item in definitions:
        try:
            tools.append(
                MCPHTTPTool(
                    name=item["name"],
                    description=item.get("description", "External MCP tool"),
                    parameters=item.get("parameters", {"type": "object"}),
                    endpoint=item["endpoint"],
                )
            )
        except KeyError as exc:
            logger.warning("Skipping MCP tool definition missing field %s: %s", exc, item)
    return tools


def _load_mcp_tools_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    tools: List[AgentTool] = []
    for item in config.get("http", []):
        try:
            tools.append(
                MCPHTTPTool(
                    name=item["name"],
                    description=item.get("description", "External MCP tool"),
                    parameters=item.get("parameters", {"type": "object"}),
                    endpoint=item["endpoint"],
                )
            )
        except KeyError as exc:
            logger.warning("Skipping HTTP tool missing field %s: %s", exc, item)
    return tools


def _discover_fastmcp_stdio_servers_from_env() -> List[AgentTool]:
    """Discover tools from FastMCP stdio servers defined in MCP_STDIO_SERVERS."""
    raw = os.getenv("MCP_STDIO_SERVERS")
    if not raw:
        return []

    try:
        definitions = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("MCP_STDIO_SERVERS is not valid JSON; skipping FastMCP stdio discovery.")
        return []

    try:
        from fastmcp import Client
        from fastmcp.client.transports import StdioTransport
    except Exception as exc:  # noqa: BLE001
        logger.warning("fastmcp not available; cannot discover MCP_STDIO_SERVERS: %s", exc)
        return []

    discovered: List[AgentTool] = []

    async def fetch_tools(transport: Any) -> List[Any]:
        client = Client(transport)
        async with client:
            return await client.list_tools()

    def _tfield(tool_def: Any, attr: str) -> Any:
        if hasattr(tool_def, attr):
            return getattr(tool_def, attr)
        if isinstance(tool_def, dict):
            return tool_def.get(attr)
        return None

    async def handle_one(item: Dict[str, Any]) -> None:
        try:
            transport = StdioTransport(
                command=item["command"],
                args=item.get("args") or [],
                env=item.get("env"),
                cwd=item.get("cwd"),
            )
            prefix = ""  # avoid prefixing tool names to keep server/tool names aligned
            tools = await fetch_tools(transport)
            for tool_def in tools:
                base_name = _tfield(tool_def, "name")
                if not base_name:
                    logger.warning("Skipping FastMCP stdio tool with missing name: %s", tool_def)
                    continue
                name = f"{prefix}{base_name}"
                description = _tfield(tool_def, "description") or ""
                params = (
                    _tfield(tool_def, "input_schema")
                    or _tfield(tool_def, "parameters")
                    or {"type": "object"}
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
        except KeyError as exc:
            logger.warning("Skipping FastMCP stdio server missing field %s: %s", exc, item)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to discover tools from FastMCP stdio server %s: %s", item, exc)

    async def gather_all() -> None:
        await asyncio.gather(*(handle_one(item) for item in definitions))

    def run_blocking(coro: Any) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return

        result: Dict[str, Any] = {}
        exc: Dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                asyncio.run(coro)
            except BaseException as e:  # noqa: BLE001
                exc["error"] = e

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "error" in exc:
            raise exc["error"]

    try:
        run_blocking(gather_all())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to discover tools from MCP_STDIO_SERVERS: %s", exc)

    return discovered


def _discover_fastmcp_stdio_servers_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    servers = config.get("stdio_servers", [])
    if not servers:
        return []

    try:
        from fastmcp import Client
        from fastmcp.client.transports import StdioTransport
    except Exception as exc:  # noqa: BLE001
        logger.warning("fastmcp not available; cannot discover MCP stdio servers from config: %s", exc)
        return []

    async def fetch_tools(transport: Any) -> List[Any]:
        client = Client(transport)
        async with client:
            return await client.list_tools()

    discovered: List[AgentTool] = []

    def _tfield(tool_def: Any, attr: str) -> Any:
        if hasattr(tool_def, attr):
            return getattr(tool_def, attr)
        if isinstance(tool_def, dict):
            return tool_def.get(attr)
        return None

    async def handle_one(item: Dict[str, Any]) -> None:
        try:
            transport = StdioTransport(
                command=item["command"],
                args=item.get("args") or [],
                env=item.get("env"),
                cwd=item.get("cwd"),
            )
            prefix = ""  # avoid prefixing tool names to keep server/tool names aligned
            tools = await fetch_tools(transport)
            for tool_def in tools:
                base_name = _tfield(tool_def, "name")
                if not base_name:
                    logger.warning("Skipping MCP stdio tool with missing name: %s", tool_def)
                    continue
                name = f"{prefix}{base_name}"
                description = _tfield(tool_def, "description") or ""
                params = (
                    _tfield(tool_def, "input_schema")
                    or _tfield(tool_def, "parameters")
                    or {"type": "object"}
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
        except KeyError as exc:
            logger.warning("Skipping MCP stdio server in config missing field %s: %s", exc, item)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to discover tools from MCP stdio server %s: %s", item, exc)

    async def gather_all() -> None:
        await asyncio.gather(*(handle_one(item) for item in servers))

    def run_blocking(coro: Any) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(coro)
            return

        exc: Dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                asyncio.run(coro)
            except BaseException as e:  # noqa: BLE001
                exc["error"] = e

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if "error" in exc:
            raise exc["error"]

    try:
        run_blocking(gather_all())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to discover tools from MCP stdio servers in config: %s", exc)

    return discovered


def _load_fastmcp_stdio_tools_from_env() -> List[AgentTool]:
    """Load FastMCP stdio tools from MCP_STDIO_TOOLS env var if provided.

    Expected format (example):
    [
      {
        "name": "utc_time",
        "description": "UTC time via FastMCP stdio server",
        "command": "uv",
        "args": ["run", "app/mcp_fast_time.py"],
        "parameters": {"type": "object", "properties": {}, "additionalProperties": false},
        "env": {},      # optional
        "cwd": "."      # optional
      }
    ]
    """
    raw = os.getenv("MCP_STDIO_TOOLS")
    if not raw:
        return []

    try:
        definitions = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("MCP_STDIO_TOOLS is not valid JSON; skipping FastMCP stdio tool registration.")
        return []

    tools: List[AgentTool] = []
    for item in definitions:
        try:
            tools.append(
                FastMCPStdioTool(
                    name=item["name"],
                    description=item.get("description", "FastMCP stdio tool"),
                    parameters=item.get("parameters", {"type": "object"}),
                    command=item["command"],
                    args=item.get("args") or [],
                    env=item.get("env"),
                    cwd=item.get("cwd"),
                )
            )
        except KeyError as exc:
            logger.warning("Skipping FastMCP stdio tool definition missing field %s: %s", exc, item)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to register FastMCP stdio tool %s: %s", item.get("name"), exc)
    return tools


def _load_fastmcp_stdio_tools_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    tools: List[AgentTool] = []
    for item in config.get("stdio_tools", []):
        try:
            tools.append(
                FastMCPStdioTool(
                    name=item["name"],
                    description=item.get("description", "FastMCP stdio tool"),
                    parameters=item.get("parameters", {"type": "object"}),
                    command=item["command"],
                    args=item.get("args") or [],
                    env=item.get("env"),
                    cwd=item.get("cwd"),
                )
            )
        except KeyError as exc:
            logger.warning("Skipping FastMCP stdio tool in config missing field %s: %s", exc, item)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to register FastMCP stdio tool from config %s: %s", item.get("name"), exc)
    return tools


def _load_mcp_config() -> Dict[str, Any]:
    """Load MCP config from TOML file specified by MCP_CONFIG_FILE (default: mcp.toml)."""
    path = Path(os.getenv("MCP_CONFIG_FILE", "mcp.toml"))
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load MCP config file %s: %s", path, exc)
        return {}


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(_build_time_tool())
    config = _load_mcp_config().get("mcp", {})

    for mcp_tool in _load_mcp_tools_from_env():
        registry.register(mcp_tool)
    for mcp_tool in _load_mcp_tools_from_config(config):
        registry.register(mcp_tool)

    for stdio_server_tool in _discover_fastmcp_stdio_servers_from_env():
        registry.register(stdio_server_tool)
    for stdio_server_tool in _discover_fastmcp_stdio_servers_from_config(config):
        registry.register(stdio_server_tool)

    for stdio_tool in _load_fastmcp_stdio_tools_from_env():
        registry.register(stdio_tool)
    for stdio_tool in _load_fastmcp_stdio_tools_from_config(config):
        registry.register(stdio_tool)
    return registry
