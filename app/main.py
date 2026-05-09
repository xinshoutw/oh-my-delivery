"""FastAPI entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin,
    cleaning,
    consumer,
    courier,
    devices,
    lists,
    onboarding,
    partner,
    restaurant,
)
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

    # 配置 CORS
    # 在「全開」模式下, allow_origins 使用 ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允許所有來源
        allow_credentials=True,
        allow_methods=["*"],  # 允許所有 HTTP 方法 (GET, POST, PUT, DELETE 等)
        allow_headers=["*"],  # 允許所有 Header
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
    app.include_router(admin.router)
    app.include_router(onboarding.router)
    app.include_router(lists.router)
    return app


app = create_app()
