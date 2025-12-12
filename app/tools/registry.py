import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

from .clients import _get_http_client, _get_process_client, MCPHttpClient, MCPProcessClient

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


class FastMCPStdioTool(AgentTool):
    """Adapter for calling a FastMCP server over stdio."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        command: str,
        args: List[str] | None = None,
        env: Dict[str, str] | None = None,
        cwd: str | None = None,
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
        headers: Dict[str, str] | None = None,
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

    def summary(self) -> List[Dict[str, str | bool]]:
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

