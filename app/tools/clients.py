import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Dict

from fastmcp import Client
from mcp.types import Implementation

_CLIENT_CACHE: Dict[str, Client] = {}
_CLIENT_CACHE_LOCK = threading.Lock()
_CLIENT_INFO = Implementation(name="bluegpt", version="1.0")


def _json_default(obj: Any) -> Any:
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "model_dump"):
        return obj.model_dump(exclude_none=True)  # type: ignore[no-any-return]
    return repr(obj)


def _spec_cache_key(spec: Any) -> str:
    try:
        payload = {"type": type(spec).__name__, "spec": spec}
        dumped = json.dumps(payload, sort_keys=True, default=_json_default, separators=(",", ":"))
    except TypeError:
        dumped = f"{type(spec).__name__}:{repr(spec)}"
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def get_client(spec: Any) -> Client:
    key = _spec_cache_key(spec)
    with _CLIENT_CACHE_LOCK:
        client = _CLIENT_CACHE.get(key)
        if client is None:
            client = Client(spec, name="bluegpt-mcp", client_info=_CLIENT_INFO)
            _CLIENT_CACHE[key] = client
        return client


async def close_all_clients() -> None:
    with _CLIENT_CACHE_LOCK:
        clients = list(_CLIENT_CACHE.values())
        _CLIENT_CACHE.clear()

    for client in clients:
        try:
            await client.close()
        except Exception:
            pass


__all__ = [
    "get_client",
    "close_all_clients",
]

