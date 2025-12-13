import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import _BaseMCPClient


_CLIENT_CACHE: Dict[str, _BaseMCPClient] = {}
_CLIENT_CACHE_LOCK = threading.Lock()


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


def _get_client(spec: Any) -> _BaseMCPClient:
    key = _spec_cache_key(spec)
    with _CLIENT_CACHE_LOCK:
        client = _CLIENT_CACHE.get(key)
        if client and client.is_running:
            return client
        client = _BaseMCPClient(spec, client_name="bluegpt-mcp")
        _CLIENT_CACHE[key] = client
        return client


__all__ = [
    "_BaseMCPClient",
    "_get_client",
]
