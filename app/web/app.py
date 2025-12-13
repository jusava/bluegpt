import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..agent import AgentManager
from ..common.config import load_samples_config, project_path
from ..tools.clients import close_all_clients
from .routes import build_router


def create_app() -> FastAPI:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger = logging.getLogger(__name__)

    manager = AgentManager()
    samples = load_samples_config()
    static_dir = project_path("app", "static")

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
        await manager.load_tools()
        logger.info("Tool registry loaded: %s", manager.registry.summary())
        try:
            yield
        finally:
            await close_all_clients()

    app = FastAPI(title="BlueGPT", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(build_router(manager=manager, samples=samples, static_dir=static_dir))
    return app
