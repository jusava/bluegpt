import asyncio
import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator, List, Optional

from dotenv import load_dotenv
from fastapi import Body, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import uvicorn

from .agent import AgentManager, AVAILABLE_MODELS, DEFAULT_SYSTEM_PROMPT, DEFAULT_REASONING, DEFAULT_VERBOSITY, DEFAULT_MAX_OUTPUT_TOKENS
from .config import load_samples_config

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="BlueGPT", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

manager = AgentManager()
logger.info("Tool registry loaded: %s", manager.registry.summary())
SAMPLES = load_samples_config()


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


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/")
async def root() -> FileResponse:
    index_path = static_dir / "index.html"
    return FileResponse(index_path)


@app.get("/api/sessions")
async def list_sessions() -> List[dict]:
    return manager.list_sessions()


@app.get("/api/tools")
async def list_tools() -> List[dict]:
    return manager.registry.summary()


@app.post("/api/tools/{name}/active")
async def set_tool_active(name: str, payload: ToolActiveUpdate) -> JSONResponse:
    try:
        manager.registry.set_active(name, payload.active)
    except KeyError:
        raise HTTPException(status_code=404, detail="Tool not found")
    return JSONResponse({"name": name, "active": payload.active})


@app.get("/api/model")
async def get_model() -> dict:
    return {"model": manager.current_model, "available": AVAILABLE_MODELS}


@app.post("/api/model")
async def set_model(payload: ModelUpdate) -> JSONResponse:
    if payload.model not in AVAILABLE_MODELS:
        raise HTTPException(status_code=400, detail="Model not supported")
    manager.current_model = payload.model
    return JSONResponse({"model": manager.current_model, "available": AVAILABLE_MODELS})


@app.get("/api/generation")
async def get_generation_settings() -> dict:
    return {
        "reasoning_effort": manager.reasoning_effort,
        "text_verbosity": manager.text_verbosity,
        "max_output_tokens": manager.max_output_tokens,
        "defaults": {
            "reasoning_effort": DEFAULT_REASONING,
            "text_verbosity": DEFAULT_VERBOSITY,
            "max_output_tokens": DEFAULT_MAX_OUTPUT_TOKENS,
        },
    }


@app.post("/api/generation")
async def set_generation_settings(payload: GenerationUpdate) -> JSONResponse:
    if payload.reasoning_effort not in {"minimal", "low", "medium", "high"}:
        raise HTTPException(status_code=400, detail="Invalid reasoning effort")
    if payload.text_verbosity not in {"low", "medium", "high"}:
        raise HTTPException(status_code=400, detail="Invalid text verbosity")
    if payload.max_output_tokens <= 0:
        raise HTTPException(status_code=400, detail="max_output_tokens must be positive")
    manager.reasoning_effort = payload.reasoning_effort
    manager.text_verbosity = payload.text_verbosity
    manager.max_output_tokens = payload.max_output_tokens
    return JSONResponse(
        {
            "reasoning_effort": manager.reasoning_effort,
            "text_verbosity": manager.text_verbosity,
            "max_output_tokens": manager.max_output_tokens,
        }
    )


@app.get("/api/samples")
async def get_samples() -> list[dict]:
    return SAMPLES


@app.get("/api/chat/{chat_id}")
async def get_chat(chat_id: str) -> JSONResponse:
    history = manager.history(chat_id)
    return JSONResponse({"chat_id": chat_id, "messages": history})


@app.post("/api/chat")
async def chat(request: ChatRequest) -> JSONResponse:
    session = manager.get_or_create(
        request.chat_id,
        system_prompt=request.system_prompt or DEFAULT_SYSTEM_PROMPT,
        model=request.model or manager.current_model,
    )
    reply = await session.run(request.message)
    return JSONResponse(
        {
            "chat_id": session.chat_id,
            "reply": reply,
            "tools": manager.registry.summary(),
        }
    )


def _chunk_text(text: str) -> List[str]:
    # Chunk by a reasonable size but prefer to split on newlines when possible.
    if not text:
        return [""]
    parts: List[str] = []
    buffer = ""
    for line in text.splitlines(keepends=True):
        if len(buffer) + len(line) > 400:
            parts.append(buffer)
            buffer = line
        else:
            buffer += line
    if buffer:
        parts.append(buffer)
    return parts or [text]


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest = Body(...)) -> EventSourceResponse:
    session = manager.get_or_create(
        request.chat_id,
        system_prompt=request.system_prompt or DEFAULT_SYSTEM_PROMPT,
        model=request.model or manager.current_model,
    )

    async def event_generator() -> AsyncGenerator[dict, None]:
        queue: asyncio.Queue[dict] = asyncio.Queue()

        async def on_event(payload: dict) -> None:
            await queue.put(payload)

        task = asyncio.create_task(session.stream_run(request.message, on_event=on_event))

        while True:
            if task.done() and queue.empty():
                break
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=0.05)
                yield {"event": payload.get("type", "status"), "data": json.dumps(payload)}
            except asyncio.TimeoutError:
                pass

        reply = await task
        for chunk in _chunk_text(reply):
            yield {"data": chunk}
            await asyncio.sleep(0.015)
        yield {"event": "done", "data": session.chat_id}

    return EventSourceResponse(event_generator())


# Convenience for local dev server: uvicorn app.main:app --reload
def run() -> None:
    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=bool(os.getenv("RELOAD", False)),
    )


if __name__ == "__main__":
    run()
