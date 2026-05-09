"""Reset all domain data — keep schema and alembic version intact.

Truncates every domain table with RESTART IDENTITY + CASCADE so the database
ends up in the same shape as a fresh `alembic upgrade head`, just empty.

Usage::

    uv run python scripts/reset_data.py
    uv run python scripts/reset_data.py --yes  # skip confirmation prompt
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Make `app` importable when invoked as `python scripts/reset_data.py`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

# Listed leaf-first; CASCADE handles any forgotten dependents anyway. Keeping
# the explicit list documents which domains the demo touches.
TABLES = (
    "sensor_events",
    "return_sessions",
    "return_boxes",
    "delivery_pin_attempts",
    "deposit_records",
    "pickup_scan_items",
    "pickup_scan_sessions",
    "order_assets",
    "dispatch_assets",
    "dispatches",
    "asset_events",
    "audit_logs",
    "asset_cycles",
    "assets",
    "orders",
    "partner_consumers",
    "consumers",
    "partners",
    "users",
    "organizations",
    "notifications",
    "chain_anchors",
    "reward_transactions",
    "washing_batch_items",
    "washing_batches",
)


def _build_url() -> str:
    # Prefer DATABASE_URL when present (matches docker-compose / app.config),
    # else fall back to local docker-compose defaults.
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    user = os.environ.get("PG_USER", "omd")
    password = os.environ.get("PG_PASSWORD", "omd")
    host = os.environ.get("PG_HOST", "localhost")
    port = os.environ.get("PG_PORT", "5432")
    db = os.environ.get("PG_DB", "omd")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


async def truncate_all(database_url: str) -> int:
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            joined = ", ".join(f'"{t}"' for t in TABLES)
            await conn.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))
    finally:
        await engine.dispose()
    return len(TABLES)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset all oh-my-delivery domain data.")
    parser.add_argument("--yes", "-y", action="store_true", help="skip confirmation prompt")
    args = parser.parse_args()

    url = _build_url()
    safe_url = url.split("@", 1)[-1] if "@" in url else url
    print(f"target database: {safe_url}")

    if not args.yes:
        confirm = input("This will TRUNCATE every domain table. Type 'reset' to continue: ")
        if confirm.strip() != "reset":
            print("aborted.")
            return 1

    n = asyncio.run(truncate_all(url))
    print(f"truncated {n} tables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
