"""Hash chain service: appends per-asset events with verifiable linkage.

Locking strategy: a row lock on the asset (``SELECT ... FOR UPDATE``) is taken
before reading the latest event hash so concurrent writers cannot fork the
chain. Callers must already be inside an open transaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import compute_event_hash
from app.core.ids import new_uuid7
from app.domain.assets.enums import ActorRole, HolderType
from app.domain.assets.models import Asset, AssetEvent, AssetEventType


class HashChainService:
    @staticmethod
    async def _lock_asset(session: AsyncSession, asset_id: uuid.UUID) -> Asset:
        stmt = select(Asset).where(Asset.id == asset_id).with_for_update()
        result = await session.execute(stmt)
        asset = result.scalar_one()
        return asset

    @staticmethod
    async def _latest_event_hash(session: AsyncSession, asset_id: uuid.UUID) -> str | None:
        stmt = (
            select(AssetEvent.event_hash)
            .where(AssetEvent.asset_id == asset_id)
            .order_by(AssetEvent.occurred_at.desc(), AssetEvent.id.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    async def append(
        cls,
        session: AsyncSession,
        *,
        asset_id: uuid.UUID,
        event_type: AssetEventType,
        actor_role: ActorRole,
        actor_id: uuid.UUID,
        cycle_id: uuid.UUID | None = None,
        from_holder_type: HolderType | None = None,
        from_holder_id: uuid.UUID | None = None,
        to_holder_type: HolderType | None = None,
        to_holder_id: uuid.UUID | None = None,
        order_id: uuid.UUID | None = None,
        pickup_session_id: uuid.UUID | None = None,
        return_session_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        lock_asset: bool = True,
    ) -> AssetEvent:
        if lock_asset:
            await cls._lock_asset(session, asset_id)

        previous_hash = await cls._latest_event_hash(session, asset_id)
        occurred = occurred_at or datetime.now(UTC)
        event_id = new_uuid7()

        canonical = cls.canonical_payload(
            event_id=event_id,
            asset_id=asset_id,
            event_type=event_type,
            actor_role=actor_role,
            from_holder_type=from_holder_type,
            to_holder_type=to_holder_type,
            occurred_at=occurred,
            metadata_keys=sorted(metadata.keys()) if metadata else [],
        )
        event_hash = compute_event_hash(canonical, previous_event_hash=previous_hash)

        event = AssetEvent(
            id=event_id,
            asset_id=asset_id,
            cycle_id=cycle_id,
            event_type=event_type,
            from_holder_type=from_holder_type,
            from_holder_id=from_holder_id,
            to_holder_type=to_holder_type,
            to_holder_id=to_holder_id,
            actor_role=actor_role,
            actor_id=actor_id,
            order_id=order_id,
            pickup_session_id=pickup_session_id,
            return_session_id=return_session_id,
            event_metadata=metadata,
            previous_event_hash=previous_hash,
            event_hash=event_hash,
            occurred_at=occurred,
            created_at=datetime.now(UTC),
        )
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    def canonical_payload(
        *,
        event_id: uuid.UUID,
        asset_id: uuid.UUID,
        event_type: AssetEventType,
        actor_role: ActorRole,
        from_holder_type: HolderType | None,
        to_holder_type: HolderType | None,
        occurred_at: datetime,
        metadata_keys: list[str],
    ) -> dict[str, Any]:
        """Canonical event payload — deliberately excludes PII.

        Holders are referenced by *type* only, never ID. Metadata contributes
        only its key set so we capture *what kind of context* exists without
        embedding values.
        """
        return {
            "event_id": str(event_id),
            "asset_id": str(asset_id),
            "event_type": event_type.value,
            "actor_role": actor_role.value,
            "from_holder_type": from_holder_type.value if from_holder_type else None,
            "to_holder_type": to_holder_type.value if to_holder_type else None,
            "occurred_at": occurred_at.astimezone(UTC).isoformat(),
            "metadata_keys": metadata_keys,
        }
