import asyncio
import json
import logging
import os
import subprocess
import threading
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

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


class MCPProcessClient:
    """Persistent stdio client for a FastMCP server using subprocess.Popen."""

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
        self.msg_id = 0
        self._lock = threading.Lock()
        self.process = subprocess.Popen(
            [self.command, *self.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={**os.environ, **env} if env else None,
            cwd=cwd,
        )
        self._handshake()

    def _send(self, method: str, params: Optional[Dict[str, Any]] = None, *, is_notification: bool = False) -> Optional[int]:
        message: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not is_notification:
            self.msg_id += 1
            message["id"] = self.msg_id
        json_line = json.dumps(message) + "\n"
        if not self.process.stdin:
            raise RuntimeError("FastMCP process stdin is unavailable")
        self.process.stdin.write(json_line)
        self.process.stdin.flush()
        return message.get("id")

    def _receive(self) -> Dict[str, Any]:
        if not self.process.stdout:
            raise RuntimeError("FastMCP process stdout is unavailable")
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError("FastMCP server closed the connection unexpectedly")
        return json.loads(line)

    def _handshake(self) -> None:
        self._send(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "bluegpt", "version": "1.0"},
            },
        )
        init_response = self._receive()
        if "error" in init_response:
            raise RuntimeError(f"FastMCP initialize failed: {init_response['error']}")
        self._send("notifications/initialized", is_notification=True)

    def _await_response(self, target_id: int) -> Dict[str, Any]:
        while True:
            response = self._receive()
            if response.get("id") == target_id:
                return response

    def list_tools(self) -> List[Dict[str, Any]]:
        with self._lock:
            req_id = self._send("tools/list")
            if req_id is None:
                raise RuntimeError("Failed to send tools/list request")
            response = self._await_response(req_id)
            if "error" in response:
                raise RuntimeError(f"tools/list failed: {response['error']}")
            result = response.get("result") or {}
            return result.get("tools") or result

    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        with self._lock:
            req_id = self._send("tools/call", {"name": tool_name, "arguments": arguments})
            if req_id is None:
                raise RuntimeError("Failed to send tools/call request")
            response = self._await_response(req_id)
            if "error" in response:
                raise RuntimeError(response["error"].get("message") or "tools/call failed")
            result = response.get("result") or {}
            content = result.get("content")
            if isinstance(content, list) and content:
                text = content[0].get("text") or content[0].get("value")
                if text is not None:
                    return str(text)
            return json.dumps(result)

    @property
    def is_running(self) -> bool:
        return self.process.poll() is None

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        if self.process.stdout:
            self.process.stdout.close()
        if self.process.stderr:
            self.process.stderr.close()
        self.process.terminate()


_CLIENT_CACHE: Dict[tuple, MCPProcessClient] = {}
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


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, AgentTool] = {}
        self._active: Dict[str, bool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool
        self._active[tool.name] = True
        logger.debug("Registered tool %s (source=%s) schema=%s", tool.name, tool.source, tool.as_response_tool())

    def list_for_responses(self) -> List[Dict[str, Any]]:
        return [tool.as_response_tool() for name, tool in self._tools.items() if self._active.get(name, True)]

    def get(self, name: str) -> AgentTool:
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' is not registered")
        return self._tools[name]

    async def execute(self, name: str, arguments: Dict[str, Any]) -> str:
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered")
        if not self._active.get(name, True):
            raise ValueError(f"Tool '{name}' is not active")
        return await self._tools[name](arguments)

    def summary(self) -> List[Dict[str, str]]:
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


def _discover_fastmcp_stdio_servers_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    servers = config.get("stdio_servers", [])
    if not servers:
        return []

    def _camel(s: str) -> str:
        parts = s.split("_")
        return parts[0] + "".join(p.capitalize() for p in parts[1:])

    def _tfield(tool_def: Any, attr: str) -> Any:
        if hasattr(tool_def, attr):
            return getattr(tool_def, attr)
        if isinstance(tool_def, dict):
            return tool_def.get(attr) or tool_def.get(_camel(attr))
        return None

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


def _load_fastmcp_stdio_tools_from_config(config: Dict[str, Any]) -> List[AgentTool]:
    return []


def _load_mcp_config() -> Dict[str, Any]:
    """Load MCP config from TOML file specified by MCP_CONFIG_FILE (default: mcp.toml)."""
    path = Path(os.getenv("MCP_CONFIG_FILE", "mcp.toml"))
    if not path.exists():
        return {}
    return tomllib.loads(path.read_text())


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    config = _load_mcp_config().get("mcp", {})

    for stdio_server_tool in _discover_fastmcp_stdio_servers_from_config(config):
        registry.register(stdio_server_tool)

    for stdio_tool in _load_fastmcp_stdio_tools_from_config(config):
        registry.register(stdio_tool)
    return registry
