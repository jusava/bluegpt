import asyncio
import json
import logging
import threading
from typing import Any, Awaitable, Callable, Dict, List

from fastmcp import Client
from mcp.types import Implementation

logger = logging.getLogger(__name__)


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


def _result_to_string(result: Any) -> str:
    """Convert a CallToolResult (or similar) into a string payload."""
    content = getattr(result, "content", None)
    if isinstance(content, list) and content:
        first = content[0]
        text = getattr(first, "text", None) or getattr(first, "value", None)
        if text is not None:
            return str(text)
    if hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(exclude_none=True, by_alias=True))
    return json.dumps(result)


class _BaseMCPClient:
    """Shared logic for FastMCP clients across transports."""

    def __init__(self, transport: Any, client_name: str) -> None:
        self.transport = transport
        self._lock = threading.Lock()
        self._runner = _LoopRunner()
        self.client = Client(
            self.transport,
            name=client_name,
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
        return _result_to_string(result)

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

    def _transport_running(self) -> bool:
        return True

    @property
    def is_running(self) -> bool:
        return self._transport_running()

