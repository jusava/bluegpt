import json
import os
from typing import Any, Dict, Optional

from fastapi import HTTPException
from openai import AsyncOpenAI

from .settings import APP_CONFIG


_client: Optional[AsyncOpenAI] = None


def parse_tool_call(call: Any) -> tuple[str, str, Dict[str, Any]]:
    call_id = str(call.call_id)
    name = str(call.name)
    raw_args = call.arguments
    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    return call_id, name, args


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set.")

        base_url = APP_CONFIG["openai_base_url"] or None
        _client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    return _client

