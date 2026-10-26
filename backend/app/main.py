"""FastAPI service. Owner: Victor (POST /analyze and POST /export land here).

Never log request bodies at any layer: they carry user images.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import VERSION, assert_startup_safe, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A failure here makes uvicorn exit non-zero before serving anything.
    assert_startup_safe(get_settings())
    yield


app = FastAPI(title="Redact", version=VERSION, lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "version": VERSION,
        "model_ids": settings.model_ids(),
        "premask": "on" if settings.premask else "off",
    }
