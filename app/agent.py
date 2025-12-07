import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import HTTPException
from openai import AsyncOpenAI

from .tools import ToolRegistry, build_default_registry

# Load .env early so environment variables are available even if main is not imported.
load_dotenv()

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are BlueGPT, a concise assistant. Use provided tools when they improve factual accuracy. "
    "Keep answers brief but helpful. If a tool call fails, explain the failure and continue."
)
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

_client: Optional[AsyncOpenAI] = None


def _extract_tool_calls(required_action: Any) -> List[Any]:
    if not required_action:
        return []
    if isinstance(required_action, dict):
        submit = required_action.get("submit_tool_outputs", {}) or {}
    else:
        submit = getattr(required_action, "submit_tool_outputs", None) or {}
    tool_calls = getattr(submit, "tool_calls", None) if not isinstance(submit, dict) else submit.get("tool_calls")
    if tool_calls is None:
        tool_calls = getattr(submit, "tool_calls", []) if not isinstance(submit, dict) else []
    return tool_calls or []


def _extract_tool_calls_from_output(output: Any) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []
    if not output or not isinstance(output, list):
        return calls
    for item in output:
        ctype = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
        if ctype != "function_call":
            continue
        name = getattr(item, "name", None) or (item.get("name") if isinstance(item, dict) else None)
        arguments = getattr(item, "arguments", None) or (item.get("arguments") if isinstance(item, dict) else None)
        call_id = getattr(item, "call_id", None) or (item.get("call_id") if isinstance(item, dict) else None) or str(uuid.uuid4())
        calls.append(
            {
                "id": call_id,
                "function": {
                    "name": name,
                    "arguments": arguments,
                },
            }
        )
    return calls


def _parse_tool_call(call: Any) -> tuple[str, str, Dict[str, Any]]:
    call_id = getattr(call, "id", None) or call.get("id") or getattr(call, "call_id", None) or call.get("call_id") or str(uuid.uuid4())
    function = getattr(call, "function", None) or call.get("function", {})
    if function:
        name = getattr(function, "name", None) or function.get("name") or "unknown_tool"
        raw_args = getattr(function, "arguments", None) or function.get("arguments") or "{}"
    else:
        name = getattr(call, "name", None) or call.get("name") or "unknown_tool"
        raw_args = getattr(call, "arguments", None) or call.get("arguments") or "{}"
    try:
        args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except Exception:  # noqa: BLE001
        args = {}
    return call_id, name, args


def _extract_text(response: Any) -> Optional[str]:
    # New Responses API may return output as list items; fall back to common shapes.
    text_parts: List[str] = []

    output = getattr(response, "output", None) or getattr(response, "output_text", None)

    if isinstance(output, str):
        text_parts.append(output)
    elif isinstance(output, list):
        for item in output:
            content_list = getattr(item, "content", None) or getattr(item, "contents", None)
            if content_list:
                for content in content_list:
                    ctype = getattr(content, "type", None) or (content.get("type") if isinstance(content, dict) else None)
                    if ctype in {"text", "output_text"}:
                        text_val = getattr(content, "text", None) or (content.get("text") if isinstance(content, dict) else None)
                        if text_val:
                            text_parts.append(str(text_val))
            ctype = getattr(item, "type", None) or (item.get("type") if isinstance(item, dict) else None)
            if ctype in {"text", "output_text"}:
                text_val = getattr(item, "text", None) or (item.get("text") if isinstance(item, dict) else None)
                if text_val:
                    text_parts.append(str(text_val))

    if text_parts:
        return "\n".join([p for p in text_parts if p])
    return None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(status_code=500, detail="OPENAI_API_KEY is not set.")
        _client = AsyncOpenAI(api_key=api_key, base_url=os.getenv("OPENAI_BASE_URL"))
    return _client


@dataclass
class AgentSession:
    chat_id: str
    registry: ToolRegistry
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    model: str = DEFAULT_MODEL
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})

    async def run(self, user_message: str) -> str:
        self.messages.append({"role": "user", "content": user_message})
        reply = await self._generate()
        self.messages.append({"role": "assistant", "content": reply})
        return reply

    async def _generate(self) -> str:
        tools = self.registry.list_for_responses() or None
        client = get_client()

        input_list: List[Dict[str, Any]] = list(self.messages)

        # Execute tool loop until the model stops requesting tools.
        while True:
            try:
                logger.debug("Creating response with model=%s tools=%d", self.model, len(tools or []))
                response = await client.responses.create(
                    model=self.model,
                    input=input_list,
                    tools=tools,
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("OpenAI responses.create failed")
                raise

            required_action = getattr(response, "required_action", None)
            tool_calls = _extract_tool_calls(required_action) or _extract_tool_calls_from_output(getattr(response, "output", None))

            if tool_calls:
                input_list.extend(getattr(response, "output", []) or [])
                tool_outputs: List[Dict[str, Any]] = []
                for call in tool_calls:
                    call_id, name, args = _parse_tool_call(call)
                    logger.debug("Tool call requested: %s args=%s", name, args)

                    try:
                        result = await self.registry.execute(name, args)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("Tool %s failed", name)
                        result = f"Tool {name} failed: {exc}"

                    tool_outputs.append({"type": "function_call_output", "call_id": call_id, "output": str(result)})
                    input_list.append(tool_outputs[-1])

                # Loop again with updated input_list containing function_call_output entries.
                continue

            text = getattr(response, "output_text", None) or _extract_text(response)
            if text is None:
                raw = None
                try:
                    raw = response.model_dump()
                except Exception:  # noqa: BLE001
                    raw = str(response)
                logger.error("Model returned no text response. Raw response: %s", raw)
                raise HTTPException(status_code=500, detail="Model returned no text response.")
            input_list.append({"role": "assistant", "content": text})
            self.messages = input_list
            return text


class AgentManager:
    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry or build_default_registry()
        self.sessions: Dict[str, AgentSession] = {}

    def get_or_create(
        self,
        chat_id: Optional[str] = None,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        model: str = DEFAULT_MODEL,
    ) -> AgentSession:
        if chat_id and chat_id in self.sessions:
            return self.sessions[chat_id]

        new_chat_id = chat_id or str(uuid.uuid4())
        session = AgentSession(
            chat_id=new_chat_id,
            registry=self.registry,
            system_prompt=system_prompt,
            model=model,
        )
        self.sessions[new_chat_id] = session
        return session

    def list_sessions(self) -> List[Dict[str, str]]:
        return [
            {"chat_id": chat_id, "title": self._title_for(session)}
            for chat_id, session in self.sessions.items()
        ]

    def _title_for(self, session: AgentSession) -> str:
        for message in session.messages:
            if message["role"] == "user":
                return (message["content"][:30] + "...") if len(message["content"]) > 30 else message["content"]
        return "New chat"

    def history(self, chat_id: str) -> List[Dict[str, str]]:
        if chat_id not in self.sessions:
            raise HTTPException(status_code=404, detail="Chat not found")
        session = self.sessions[chat_id]
        # Only return user/assistant text messages; skip system/tool metadata.
        view: List[Dict[str, str]] = []
        for msg in session.messages:
            if msg["role"] not in {"user", "assistant"}:
                continue
            content = msg.get("content")
            if not content:
                continue
            view.append({"role": msg["role"], "content": str(content)})
        return view
