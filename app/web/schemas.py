from typing import Optional
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    message: str = Field(..., description="User message text")
    chat_id: Optional[str] = Field(None, description="Existing chat identifier")
    system_prompt: Optional[str] = Field(None, description="Override system prompt for a new chat")
    model: Optional[str] = Field(None, description="Override model name for this request")


class ToolActiveUpdate(BaseModel):
    active: bool


class ModelUpdate(BaseModel):
    model: str


class GenerationUpdate(BaseModel):
    reasoning_effort: str
    text_verbosity: str
    max_output_tokens: int
