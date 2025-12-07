import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import HTTPException
from openai import AsyncOpenAI

from .config import load_app_config, load_prompts_config
from .tools import ToolRegistry, build_default_registry
from openai.types.shared_params.reasoning import Reasoning


# Load .env early so environment variables are available even if main is not imported.
load_dotenv()

logger = logging.getLogger(__name__)

APP_CONFIG = load_app_config()
PROMPTS_CONFIG = load_prompts_config()

DEFAULT_SYSTEM_PROMPT = PROMPTS_CONFIG.get("system")
DEFAULT_MODEL = APP_CONFIG.get("default_model", "gpt-5-mini")
AVAILABLE_MODELS = APP_CONFIG.get("available_models", ["gpt-5.1", "gpt-5-mini"])
DEFAULT_REASONING = APP_CONFIG.get("reasoning_effort", "none")
DEFAULT_VERBOSITY = APP_CONFIG.get("text_verbosity", "low")
DEFAULT_MAX_OUTPUT_TOKENS = APP_CONFIG.get("max_output_tokens", 1000)
REASONING_OPTIONS = APP_CONFIG.get(
    "reasoning_effort_options",
    {
        "gpt-5.1": ["none", "low", "medium", "high"],
        "gpt-5-mini": ["minimal", "low", "medium", "high"],
    },
)

_client: Optional[AsyncOpenAI] = None


def _parse_tool_call(call: Any) -> tuple[str, str, Dict[str, Any]]:
    call_id = str(call.call_id)
    name = str(call.name)
    raw_args = call.arguments

    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)

    return call_id, name, args


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
    reasoning_effort: str = DEFAULT_REASONING
    text_verbosity: str = DEFAULT_VERBOSITY
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    messages: List[Any] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.messages:
            self.messages.append({"role": "system", "content": self.system_prompt})

    async def run(self, user_message: str) -> str:
        # Collect all chunks from the stream for the final reply
        reply = ""
        async for event in self.stream_run(user_message):
            if event["type"] == "text":
                reply += event["content"]
        return reply

    async def stream_run(self, user_message: str) -> AsyncGenerator[Dict[str, Any], None]:
        self.messages.append({"role": "user", "content": user_message})
        async for event in self._generate():
            yield event

    async def _generate(self) -> AsyncGenerator[Dict[str, Any], None]:
        # Local loop for tool calls
        while True:
            tools: List[Dict[str, Any]] = self.registry.list_for_responses() or []
            tools_param = tools or None
            input_list: List[Any] = self.messages

            client = get_client()
            logger.info("Values: model=%s effort=%s", self.model, self.reasoning_effort)
            # yield {"type": "text", "content": f"[DEBUG] Model: {self.model}, Effort: {self.reasoning_effort}\n\n"}
            
            logger.debug("Creating response with model=%s tools=%d", self.model, len(tools or []))
            
            response = await client.responses.create(
                model=self.model,
                input=input_list,
                tools=tools_param,
                reasoning=Reasoning(effort=self.reasoning_effort, summary="auto"),
                max_output_tokens=self.max_output_tokens,
            )

            # Update input list with new items
            input_list.extend(response.output)

            called_tools = False

            for item in response.output:
                if item.type == "reasoning":
                    yield {"type": "reasoning", "reasoning": item.model_dump(exclude_none=True)}
                    continue
                
                if item.type == "function_call":
                    call_id, name, args = _parse_tool_call(item)
                    yield {"type": "tool_start", "name": name, "arguments": args}

                    result = await self.registry.execute(name, args)
                    yield {"type": "tool_result", "name": name, "output": result}
                    
                    # Append result to input list for next turn
                    input_list.append({"type": "function_call_output", "call_id": call_id, "output": str(result)})
                    called_tools = True

            if called_tools:
                continue

            # Final text response
            input_list.append({"role": "assistant", "content": response.output_text})
            yield {"type": "text", "content": response.output_text}
            return


class AgentManager:
    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry or build_default_registry()
        self.sessions: Dict[str, AgentSession] = {}
        self.current_model = DEFAULT_MODEL
        self.reasoning_effort = DEFAULT_REASONING
        self.text_verbosity = DEFAULT_VERBOSITY
        self.max_output_tokens = DEFAULT_MAX_OUTPUT_TOKENS
        self.reasoning_options: Dict[str, List[str]] = REASONING_OPTIONS

    def get_or_create(
        self,
        chat_id: Optional[str] = None,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        model: str = DEFAULT_MODEL,
    ) -> AgentSession:
        if chat_id and chat_id in self.sessions:
            session = self.sessions[chat_id]
            # Update session with current manager settings to ensure propagation
            session.model = model or self.current_model
            session.reasoning_effort = self.reasoning_effort
            session.text_verbosity = self.text_verbosity
            session.max_output_tokens = self.max_output_tokens
            return session

        new_chat_id = chat_id or str(uuid.uuid4())
        session = AgentSession(
            chat_id=new_chat_id,
            registry=self.registry,
            system_prompt=system_prompt,
            model=model or self.current_model,
            reasoning_effort=self.reasoning_effort,
            text_verbosity=self.text_verbosity,
            max_output_tokens=self.max_output_tokens,
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
            role = message.get("role") if isinstance(message, dict) else getattr(message, "role", None)
            if role == "user":
                content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
                if isinstance(content, str) and len(content) > 30:
                    return content[:30] + "..."
                return str(content)
        return "New chat"

    def history(self, chat_id: str) -> List[Dict[str, str]]:
        if chat_id not in self.sessions:
            raise HTTPException(status_code=404, detail="Chat not found")
        session = self.sessions[chat_id]
        # Only return user/assistant text messages; skip system/tool metadata.
        view: List[Dict[str, str]] = []
        for msg in session.messages:
            role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
            if role not in {"user", "assistant"}:
                continue
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
            if not content:
                continue
            view.append({"role": str(role), "content": str(content)})
        return view
