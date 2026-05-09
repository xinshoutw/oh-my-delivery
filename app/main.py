"""FastAPI entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import cleaning, consumer, courier, devices, partner, restaurant
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="oh-my-delivery — Reusable Container Responsibility Platform",
        version="0.1.0",
        debug=settings.debug,
        lifespan=lifespan,
    )

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.env}

    app.include_router(cleaning.router)
    app.include_router(restaurant.router)
    app.include_router(partner.router)
    app.include_router(courier.router)
    app.include_router(consumer.router)
    app.include_router(devices.router)
    return app


app = create_app()
