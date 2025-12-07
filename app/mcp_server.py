from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Sample MCP HTTP Tool", version="0.1.0")


class ToolRequest(BaseModel):
    tool: str
    arguments: Dict[str, Any] | None = None


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/tools/utc_time")
async def utc_time(_: ToolRequest) -> dict:
    """Return the current UTC time ISO string."""
    now = datetime.now(timezone.utc).isoformat()
    return {"result": now}


def run() -> None:
    import uvicorn

    uvicorn.run("app.mcp_server:app", host="0.0.0.0", port=9000, reload=True)


if __name__ == "__main__":
    run()
