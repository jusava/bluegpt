import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List

from openai.types.shared_params.reasoning import Reasoning

from ..tools import ToolRegistry
from .settings import (
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_REASONING,
    DEFAULT_SYSTEM_PROMPT,
    DEFAULT_VERBOSITY,
)
from .utils import get_openai_client, parse_tool_call

logger = logging.getLogger(__name__)


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
        while True:
            tools = self.registry.list_for_responses() or []
            tools_param = tools or None
            input_list: List[Any] = self.messages

            client = get_openai_client()
            logger.debug("Creating response with model=%s tools=%d", self.model, len(tools or []))

            response = await client.responses.create(
                model=self.model,
                input=input_list,
                tools=tools_param,
                reasoning=Reasoning(effort=self.reasoning_effort, summary="auto"),
                max_output_tokens=self.max_output_tokens,
            )

            input_list.extend(response.output)

            called_tools = False
            for item in response.output:
                if item.type == "reasoning":
                    yield {"type": "reasoning", "reasoning": item.model_dump(exclude_none=True)}
                    continue

                if item.type == "function_call":
                    call_id, name, args = parse_tool_call(item)
                    yield {"type": "tool_start", "name": name, "arguments": args}

                    result = await self.registry.execute(name, args)
                    yield {"type": "tool_result", "name": name, "output": result}

                    input_list.append({"type": "function_call_output", "call_id": call_id, "output": str(result)})
                    called_tools = True

            if called_tools:
                continue

            input_list.append({"role": "assistant", "content": response.output_text})
            yield {"type": "text", "content": response.output_text}
            return

