import asyncio
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

from .agent import AgentManager, DEFAULT_MODEL, DEFAULT_SYSTEM_PROMPT

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


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message text")
    chat_id: Optional[str] = Field(None, description="Existing chat identifier")
    system_prompt: Optional[str] = Field(None, description="Override system prompt for a new chat")
    model: Optional[str] = Field(None, description="Override model name for this request")


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


@app.get("/api/chat/{chat_id}")
async def get_chat(chat_id: str) -> JSONResponse:
    history = manager.history(chat_id)
    return JSONResponse({"chat_id": chat_id, "messages": history})


@app.post("/api/chat")
async def chat(request: ChatRequest) -> JSONResponse:
    try:
        session = manager.get_or_create(
            request.chat_id,
            system_prompt=request.system_prompt or DEFAULT_SYSTEM_PROMPT,
            model=request.model or DEFAULT_MODEL,
        )
        reply = await session.run(request.message)
        return JSONResponse({"chat_id": session.chat_id, "reply": reply, "tools": manager.registry.summary()})
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat request failed")
        raise HTTPException(status_code=500, detail=str(exc))


def _chunk_text(text: str, size: int = 20) -> List[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest = Body(...)) -> EventSourceResponse:
    session = manager.get_or_create(
        request.chat_id,
        system_prompt=request.system_prompt or DEFAULT_SYSTEM_PROMPT,
        model=request.model or DEFAULT_MODEL,
    )

    async def event_generator() -> AsyncGenerator[dict, None]:
        try:
            reply = await session.run(request.message)
            for chunk in _chunk_text(reply):
                yield {"data": chunk}
                await asyncio.sleep(0.015)
            yield {"event": "done", "data": session.chat_id}
        except HTTPException as exc:
            yield {"event": "error", "data": exc.detail}
        except Exception as exc:  # noqa: BLE001
            yield {"event": "error", "data": str(exc)}

    return EventSourceResponse(event_generator())


# Convenience for local dev server: uvicorn app.main:app --reload
def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=bool(os.getenv("RELOAD", False)),
    )


if __name__ == "__main__":
    run()
