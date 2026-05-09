"""ReturnService — consumer scan path (D11)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.hashing import hash_asset_token, hash_short_code
from app.core.ids import new_uuid7
from app.domain.assets.enums import (
    ActorRole,
    AssetStatus,
    HolderType,
)
from app.domain.assets.models import Asset, AssetEventType
from app.domain.assets.state_machine import assert_transition
from app.domain.audit.service import AuditService
from app.domain.devices.models import ReturnBox
from app.domain.hashchain.service import HashChainService
from app.domain.returns.models import ReturnSession, ReturnSessionStatus


@dataclass(frozen=True)
class ScanResult:
    session: ReturnSession
    asset: Asset
    is_current_holder: bool


class ReturnService:
    @staticmethod
    async def scan(
        session: AsyncSession,
        *,
        consumer_id: uuid.UUID,
        return_box_id: uuid.UUID,
        asset_token: str | None,
        short_code: str | None,
    ) -> ScanResult:
        if not asset_token and not short_code:
            raise HTTPException(status_code=400, detail="asset_token or short_code required")

        return_box = await _load_return_box(session, return_box_id)
        if not return_box.active:
            raise HTTPException(status_code=409, detail="return box not active")

        asset = await _resolve_asset(session, asset_token=asset_token, short_code=short_code)
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")

        if asset.status != AssetStatus.WITH_CONSUMER:
            raise HTTPException(
                status_code=409,
                detail=f"asset is {asset.status.value}; cannot scan for return",
            )

        is_current_holder = (
            asset.responsible_party_type == HolderType.CONSUMER
            and asset.responsible_party_id == consumer_id
        )

        # Reuse an active session at the same box for the same asset, if any.
        now = datetime.now(UTC)
        existing = (
            await session.execute(
                select(ReturnSession)
                .where(
                    ReturnSession.asset_id == asset.id,
                    ReturnSession.status == ReturnSessionStatus.SCANNED,
                    ReturnSession.return_box_id == return_box_id,
                    ReturnSession.expires_at > now,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if existing is not None:
            return ScanResult(session=existing, asset=asset, is_current_holder=is_current_holder)

        settings = get_settings()
        assert_transition(asset.status, AssetStatus.RETURN_PENDING_DEPOSIT, ActorRole.CONSUMER)
        asset.status = AssetStatus.RETURN_PENDING_DEPOSIT
        asset.physical_holder_type = HolderType.CONSUMER
        asset.physical_holder_id = consumer_id
        session.add(asset)

        new_session = ReturnSession(
            id=new_uuid7(),
            asset_id=asset.id,
            scanned_by_consumer_id=consumer_id,
            responsible_consumer_id=asset.responsible_party_id
            if asset.responsible_party_type == HolderType.CONSUMER
            else None,
            return_box_id=return_box_id,
            status=ReturnSessionStatus.SCANNED,
            scanned_at=now,
            expires_at=now + timedelta(seconds=settings.return_session_ttl_seconds),
            created_at=now,
        )
        session.add(new_session)

        await HashChainService.append(
            session,
            asset_id=asset.id,
            event_type=AssetEventType.CONSUMER_RETURN_SCANNED,
            actor_role=ActorRole.CONSUMER,
            actor_id=consumer_id,
            cycle_id=asset.current_cycle_id,
            from_holder_type=HolderType.CONSUMER,
            from_holder_id=consumer_id,
            to_holder_type=HolderType.CONSUMER,
            to_holder_id=consumer_id,
            return_session_id=new_session.id,
            occurred_at=now,
            lock_asset=False,
            metadata={"return_box_id": str(return_box_id)},
        )

        await AuditService.record(
            session,
            actor_type=ActorRole.CONSUMER.value,
            actor_id=consumer_id,
            action="return.scan",
            target_type="return_session",
            target_id=new_session.id,
            after={
                "asset_id": str(asset.id),
                "return_box_id": str(return_box_id),
                "is_current_holder": is_current_holder,
            },
        )
        await session.flush()
        return ScanResult(session=new_session, asset=asset, is_current_holder=is_current_holder)

    @staticmethod
    async def cancel(
        session: AsyncSession,
        *,
        return_session_id: uuid.UUID,
        consumer_id: uuid.UUID,
    ) -> ReturnSession:
        rs = (
            await session.execute(
                select(ReturnSession).where(ReturnSession.id == return_session_id).with_for_update()
            )
        ).scalar_one_or_none()
        if rs is None:
            raise HTTPException(status_code=404, detail="return session not found")
        if rs.scanned_by_consumer_id != consumer_id:
            raise HTTPException(status_code=403, detail="not your return session")
        if rs.status != ReturnSessionStatus.SCANNED:
            raise HTTPException(status_code=409, detail=f"session is {rs.status.value}")

        # Roll the asset back to with_consumer if it's still in our pending state.
        asset = (
            await session.execute(select(Asset).where(Asset.id == rs.asset_id).with_for_update())
        ).scalar_one()
        if asset.status == AssetStatus.RETURN_PENDING_DEPOSIT:
            asset.status = AssetStatus.WITH_CONSUMER
            session.add(asset)

        rs.status = ReturnSessionStatus.CANCELLED
        rs.cancelled_at = datetime.now(UTC)
        session.add(rs)
        await session.flush()
        return rs


async def _load_return_box(session: AsyncSession, return_box_id: uuid.UUID) -> ReturnBox:
    box = (
        await session.execute(select(ReturnBox).where(ReturnBox.id == return_box_id))
    ).scalar_one_or_none()
    if box is None:
        raise HTTPException(status_code=404, detail="return box not found")
    return box


async def _resolve_asset(
    session: AsyncSession,
    *,
    asset_token: str | None,
    short_code: str | None,
) -> Asset | None:
    settings = get_settings()
    if asset_token:
        token_hash = hash_asset_token(asset_token, settings.server_secret)
        return (
            await session.execute(select(Asset).where(Asset.token_hash == token_hash))
        ).scalar_one_or_none()
    assert short_code is not None
    sc_hash = hash_short_code(short_code.strip().upper())
    return (
        await session.execute(select(Asset).where(Asset.short_code_hash == sc_hash))
    ).scalar_one_or_none()
