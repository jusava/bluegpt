import threading
from typing import Any, Dict, List, Optional

from .http import MCPHttpClient
from .stdio import MCPProcessClient


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


__all__ = [
    "MCPProcessClient",
    "MCPHttpClient",
    "_get_process_client",
    "_get_http_client",
]
