"""HashChainAnchorService — daily Merkle root over the previous day's events."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_uuid7
from app.domain.assets.models import AssetEvent
from app.domain.hashchain.anchor_models import ChainAnchor


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def merkle_root(hashes: list[str]) -> str:
    if not hashes:
        return _sha256("EMPTY")
    layer = list(hashes)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        layer = [_sha256(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


class HashChainAnchorService:
    @staticmethod
    async def compute_for_date(
        session: AsyncSession,
        anchor_date: date,
    ) -> ChainAnchor:
        start = datetime.combine(anchor_date, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)

        rows = list(
            (
                await session.execute(
                    select(AssetEvent.id, AssetEvent.event_hash)
                    .where(
                        AssetEvent.occurred_at >= start,
                        AssetEvent.occurred_at < end,
                    )
                    .order_by(AssetEvent.occurred_at.asc(), AssetEvent.id.asc())
                )
            ).all()
        )
        first_id = rows[0][0] if rows else None
        last_id = rows[-1][0] if rows else None
        root = merkle_root([row[1] for row in rows])

        anchor = ChainAnchor(
            id=new_uuid7(),
            anchor_date=anchor_date,
            root_hash=root,
            event_count=len(rows),
            first_event_id=first_id,
            last_event_id=last_id,
            created_at=datetime.now(UTC),
        )
        session.add(anchor)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            existing = (
                await session.execute(
                    select(ChainAnchor).where(ChainAnchor.anchor_date == anchor_date)
                )
            ).scalar_one()
            if existing.root_hash != root:
                # The chain diverged for an already-anchored day — flag loudly.
                raise ValueError(
                    f"chain anchor mismatch for {anchor_date}: "
                    f"existing={existing.root_hash} new={root}"
                ) from None
            return existing
        return anchor
