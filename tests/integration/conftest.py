"""Integration test fixtures: dedicated test database with per-test rollback."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

os.environ.setdefault("SERVER_SECRET", "x" * 32)
os.environ.setdefault("JWT_SECRET", "y" * 32)
os.environ.setdefault("ENV", "test")

TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "omd_test")
PG_HOST = os.environ.get("PG_HOST", "localhost")
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_USER = os.environ.get("PG_USER", "omd")
PG_PASSWORD = os.environ.get("PG_PASSWORD", "omd")

ADMIN_URL = f"postgresql+asyncpg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/postgres"
TEST_URL = f"postgresql+asyncpg://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{TEST_DB_NAME}"

os.environ["DATABASE_URL"] = TEST_URL


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    admin = create_async_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB_NAME}"'))
        await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    await admin.dispose()

    from app.db.base import import_all_models

    import_all_models()

    engine = create_async_engine(TEST_URL, future=True, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine
    await engine.dispose()


_TABLES_TO_CLEAR = (
    "asset_events",
    "audit_logs",
    "asset_cycles",
    "assets",
)


@pytest_asyncio.fixture(loop_scope="session")
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Function-scoped session.

    Truncates all tables after each test for isolation. Cheaper than
    nested-savepoint gymnastics with asyncpg, and the test DB is empty at the
    start of each test regardless of how the previous one terminated.
    """
    sessionmaker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with sessionmaker() as session:
        try:
            yield session
        finally:
            await session.close()

    cleanup_conn: AsyncConnection
    async with test_engine.begin() as cleanup_conn:
        joined = ", ".join(f'"{t}"' for t in _TABLES_TO_CLEAR)
        await cleanup_conn.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))


@pytest_asyncio.fixture(loop_scope="session")
async def api_client(
    test_engine: AsyncEngine,
) -> AsyncIterator[AsyncClient]:
    """ASGI HTTP client with `get_db_session` overridden to use the test engine."""
    from app.api.deps import get_db_session
    from app.main import create_app

    app = create_app()

    sessionmaker = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = _override_session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    async with test_engine.begin() as conn:
        joined = ", ".join(f'"{t}"' for t in _TABLES_TO_CLEAR)
        await conn.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))
