import logging
import asyncio
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

from .clients import _get_client

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


class _FastMCPRemoteTool(AgentTool):
    """Shared adapter for calling a FastMCP server over any transport."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        *,
        client_getter: Callable[[], Any],
        source: str,
    ) -> None:
        self._client_getter = client_getter
        super().__init__(name=name, description=description, parameters=parameters, handler=self._call)
        self.source = source

    async def _call(self, arguments: Dict[str, Any]) -> str:
        client = self._client_getter()
        return await asyncio.to_thread(client.call_tool, self.name, arguments or {})


class FastMCPTool(_FastMCPRemoteTool):
    """Adapter for calling a FastMCP server using FastMCP Client inference."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        *,
        client_spec: Any,
        source: str,
    ) -> None:
        self.client_spec = client_spec
        super().__init__(
            name=name,
            description=description,
            parameters=parameters,
            client_getter=lambda: _get_client(client_spec),
            source=source,
        )


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
