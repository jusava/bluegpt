import asyncio
import json
import logging
import os
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
from mcp.types import Implementation

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

    def as_response_tool(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class _LoopRunner:
    """Run async FastMCP client operations on a dedicated, long-lived event loop."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._ready.wait()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def run(self, coro: Awaitable[Any]) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def close(self) -> None:
        try:
            self._loop.call_soon_threadsafe(self._loop.stop)
        finally:
            self._thread.join(timeout=2)
            self._loop.close()


class MCPProcessClient:
    """Persistent stdio client for a FastMCP server using the official FastMCP Client."""

    def __init__(
        self,
        command: str,
        args: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> None:
        self.command = command
        self.args = args or []
        self.env = env
        self.cwd = cwd
        self._lock = threading.Lock()
        self._runner = _LoopRunner()

        # StdioTransport handles subprocess lifecycle and protocol details.
        self.transport = StdioTransport(
            command=self.command,
            args=self.args,
            env=env,
            cwd=cwd,
            keep_alive=True,
        )
        self.client = Client(
            self.transport,
            name="bluegpt-stdio",
            client_info=Implementation(name="bluegpt", version="1.0"),
        )

    def _run(self, async_fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        """Run an async FastMCP client call on the dedicated loop."""
        return self._runner.run(async_fn(*args, **kwargs))

    def list_tools(self) -> List[Any]:
        async def _list() -> List[Any]:
            async with self.client:
                return await self.client.list_tools()

        with self._lock:
            return self._run(_list)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        async def _call() -> Any:
            async with self.client:
                return await self.client.call_tool(tool_name, arguments or {})

        with self._lock:
            result = self._run(_call)

        # FastMCP returns a CallToolResult with typed content items.
        content = getattr(result, "content", None)
        if isinstance(content, list) and content:
            first = content[0]
            text = getattr(first, "text", None) or getattr(first, "value", None)
            if text is not None:
                return str(text)

        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(exclude_none=True, by_alias=True))
        return json.dumps(result)

    @property
    def is_running(self) -> bool:
        task = getattr(self.transport, "_connect_task", None)
        if task is None:
            return True
        return not task.done()

    def close(self) -> None:
        async def _close() -> None:
            await self.client.close()

        with self._lock:
            try:
                self._run(_close)
            except Exception:
                logger.debug("Error closing FastMCP client", exc_info=True)
            finally:
                self._runner.close()


class MCPHttpClient:
    """Persistent HTTP client for a FastMCP server using the official FastMCP Client."""

    def __init__(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        auth: Any = None,
        sse_read_timeout: Any = None,
    ) -> None:
        self.url = url
        self.headers = headers
        self.auth = auth
        self.sse_read_timeout = sse_read_timeout
        self._lock = threading.Lock()
        self._runner = _LoopRunner()

        self.transport = StreamableHttpTransport(
            url=self.url,
            headers=headers,
            auth=auth,
            sse_read_timeout=sse_read_timeout,
        )
        self.client = Client(
            self.transport,
            name="bluegpt-http",
            client_info=Implementation(name="bluegpt", version="1.0"),
        )

    def _run(self, async_fn: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any) -> Any:
        return self._runner.run(async_fn(*args, **kwargs))

    def list_tools(self) -> List[Any]:
        async def _list() -> List[Any]:
            async with self.client:
                return await self.client.list_tools()

        with self._lock:
            return self._run(_list)

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        async def _call() -> Any:
            async with self.client:
                return await self.client.call_tool(tool_name, arguments or {})

        with self._lock:
            result = self._run(_call)

        content = getattr(result, "content", None)
        if isinstance(content, list) and content:
            first = content[0]
            text = getattr(first, "text", None) or getattr(first, "value", None)
            if text is not None:
                return str(text)

        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(exclude_none=True, by_alias=True))
        return json.dumps(result)

    @property
    def is_running(self) -> bool:
        return True

    def close(self) -> None:
        async def _close() -> None:
            await self.client.close()

        with self._lock:
            try:
                self._run(_close)
            except Exception:
                logger.debug("Error closing FastMCP HTTP client", exc_info=True)
            finally:
                self._runner.close()


_CLIENT_CACHE: Dict[tuple, MCPProcessClient] = {}
_HTTP_CLIENT_CACHE: Dict[tuple, MCPHttpClient] = {}
_CLIENT_CACHE_LOCK = threading.Lock()


def _client_cache_key(command: str, args: Optional[List[str]], env: Optional[Dict[str, str]], cwd: Optional[str]) -> tuple:
    env_items = tuple(sorted((env or {}).items()))
    return (command, tuple(args or []), env_items, cwd)


def _get_process_client(command: str, args: Optional[List[str]], env: Optional[Dict[str, str]], cwd: Optional[str]) -> MCPProcessClient:
    key = _client_cache_key(command, args, env, cwd)
    with _CLIENT_CACHE_LOCK:
        client = _CLIENT_CACHE.get(key)
        if client and client.is_running:
            return client
        client = MCPProcessClient(command, args, env, cwd)
        _CLIENT_CACHE[key] = client
        return client


def _http_client_cache_key(
    url: str,
    headers: Optional[Dict[str, str]],
    auth: Any,
    sse_read_timeout: Any,
) -> tuple:
    headers_items = tuple(sorted((headers or {}).items()))
    return (url, headers_items, str(auth) if auth is not None else None, sse_read_timeout)


def _get_http_client(
    url: str,
    headers: Optional[Dict[str, str]],
    auth: Any,
    sse_read_timeout: Any,
) -> MCPHttpClient:
    key = _http_client_cache_key(url, headers, auth, sse_read_timeout)
    with _CLIENT_CACHE_LOCK:
        client = _HTTP_CLIENT_CACHE.get(key)
        if client and client.is_running:
            return client
        client = MCPHttpClient(url, headers=headers, auth=auth, sse_read_timeout=sse_read_timeout)
        _HTTP_CLIENT_CACHE[key] = client
        return client


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

    def _client(self) -> MCPProcessClient:
        return _get_process_client(self.command, self.args, self.env, self.cwd)

    async def _call_stdio(self, arguments: Dict[str, Any]) -> str:
        client = self._client()
        return await asyncio.to_thread(client.call_tool, self.name, arguments or {})


class FastMCPHttpTool(AgentTool):
    """Adapter for calling a FastMCP server over Streamable HTTP."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        url: str,
        headers: Optional[Dict[str, str]] = None,
        auth: Any = None,
        sse_read_timeout: Any = None,
    ) -> None:
        self.url = url
        self.headers = headers
        self.auth = auth
        self.sse_read_timeout = sse_read_timeout

        super().__init__(name=name, description=description, parameters=parameters, handler=self._call_http)
        self.source = "mcp-http"

    def _client(self) -> MCPHttpClient:
        return _get_http_client(self.url, self.headers, self.auth, self.sse_read_timeout)

    async def _call_http(self, arguments: Dict[str, Any]) -> str:
        client = self._client()
        return await asyncio.to_thread(client.call_tool, self.name, arguments or {})


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, AgentTool] = {}
        self._active: Dict[str, bool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool
        self._active[tool.name] = True
        logger.debug("Registered tool %s (source=%s) schema=%s", tool.name, tool.source, tool.as_response_tool())

    def list_for_responses(self) -> List[Dict[str, Any]]:
        return [
            tool.as_response_tool() 
            for name, tool in self._tools.items() 
            if self._active.get(name, True)
            ]

    def get(self, name: str) -> AgentTool:
        return self._tools[name]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        return await self._tools[name](arguments)

    def summary(self) -> List[Dict[str, str|bool]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "source": tool.source,
                "active": self._active.get(tool.name, True),
            }
            for tool in self._tools.values()
        ]

    def set_active(self, name: str, active: bool) -> None:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered")
        self._active[name] = bool(active)


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
        prefix = ""  # avoid prefixing tool names to keep server/tool names aligned
        tools = client.list_tools()
        for tool_def in tools:
            base_name = _tfield(tool_def, "name")
            if not base_name:
                raise ValueError(f"MCP stdio tool missing name: {tool_def}")
            name = f"{prefix}{base_name}"
            description = _tfield(tool_def, "description") or ""
            params = _tfield(tool_def, "input_schema") or _tfield(tool_def, "parameters") or {"type": "object", "additionalProperties": True}
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
            params = _tfield(tool_def, "input_schema") or _tfield(tool_def, "parameters") or {"type": "object", "additionalProperties": True}
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


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    config = _normalize_mcp_config(_load_mcp_config())

    for stdio_server_tool in _discover_fastmcp_stdio_servers_from_config(config):
        registry.register(stdio_server_tool)

    for http_server_tool in _discover_fastmcp_http_servers_from_config(config):
        registry.register(http_server_tool)

    for stdio_tool in _load_fastmcp_stdio_tools_from_config(config):
        registry.register(stdio_tool)
    return registry
