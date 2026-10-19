import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import api
from .config import settings
from .ollama_client import OllamaClient
from .ratelimit import GpuGate, SlidingWindow

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = httpx.AsyncClient(
        base_url=settings.ollama_url,
        timeout=httpx.Timeout(connect=5.0, read=settings.line_timeout_s, write=10.0, pool=5.0),
    )
    app.state.ollama = OllamaClient(client)
    warmup = asyncio.create_task(app.state.ollama.warmup())
    yield
    warmup.cancel()
    await client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.rpm = SlidingWindow(settings.rate_rpm, 60.0)
    app.state.gate = GpuGate(settings.max_queue)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(api.router)
    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    return app


app = create_app()
