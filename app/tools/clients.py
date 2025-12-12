import asyncio
import json
import logging
import threading
from typing import Any, Awaitable, Callable, Dict, List, Optional

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport
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


class MCPProcessClient(_BaseMCPClient):
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

        transport = StdioTransport(
            command=self.command,
            args=self.args,
            env=env,
            cwd=cwd,
            keep_alive=True,
        )
        super().__init__(transport, client_name="bluegpt-stdio")

    def _transport_running(self) -> bool:
        task = getattr(self.transport, "_connect_task", None)
        if task is None:
            return True
        return not task.done()

class MCPHttpClient(_BaseMCPClient):
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

        transport = StreamableHttpTransport(
            url=self.url,
            headers=headers,
            auth=auth,
            sse_read_timeout=sse_read_timeout,
        )
        super().__init__(transport, client_name="bluegpt-http")


_CLIENT_CACHE: Dict[tuple, MCPProcessClient] = {}
_HTTP_CLIENT_CACHE: Dict[tuple, MCPHttpClient] = {}
_CLIENT_CACHE_LOCK = threading.Lock()


def _client_cache_key(
    command: str,
    args: Optional[List[str]],
    env: Optional[Dict[str, str]],
    cwd: Optional[str],
) -> tuple:
    env_items = tuple(sorted((env or {}).items()))
    return (command, tuple(args or []), env_items, cwd)


def _get_process_client(
    command: str,
    args: Optional[List[str]],
    env: Optional[Dict[str, str]],
    cwd: Optional[str],
) -> MCPProcessClient:
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
