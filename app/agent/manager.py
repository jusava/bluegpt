import uuid
from typing import Dict, List, Optional

from fastapi import HTTPException

from ..tools import ToolRegistry, build_default_registry
from .session import AgentSession
from .settings import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_REASONING,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_VERBOSITY,
    REASONING_OPTIONS,
)


class AgentManager:
    def __init__(self, registry: Optional[ToolRegistry] = None) -> None:
        self.registry = registry or ToolRegistry()
        self.sessions: Dict[str, AgentSession] = {}
        self.current_model = DEFAULT_MODEL
        self.reasoning_effort = DEFAULT_REASONING
        self.text_verbosity = DEFAULT_VERBOSITY
        self.max_output_tokens = DEFAULT_MAX_OUTPUT_TOKENS
        self.reasoning_options: Dict[str, List[str]] = REASONING_OPTIONS

    async def load_tools(self) -> None:
        self.registry = await build_default_registry()
        for session in self.sessions.values():
            session.registry = self.registry

    def get_or_create(
        self,
        chat_id: Optional[str] = None,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        model: str = DEFAULT_MODEL,
    ) -> AgentSession:
        if chat_id and chat_id in self.sessions:
            session = self.sessions[chat_id]
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

