"""ReturnBox + sensor event ingestion service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import hmac_sha256_hex
from app.core.ids import new_uuid7
from app.domain.assets.enums import (
    ActorRole,
    AssetStatus,
    HolderType,
)
from app.domain.assets.models import Asset, AssetEventType
from app.domain.assets.state_machine import assert_transition
from app.domain.devices.models import ReturnBox, SensorEvent
from app.domain.hashchain.service import HashChainService
from app.domain.returns.models import ReturnSession, ReturnSessionStatus


def hash_device_key(api_key: str, server_secret: str) -> str:
    return hmac_sha256_hex(api_key, server_secret)


@dataclass(frozen=True)
class IngestResult:
    sensor_event: SensorEvent
    duplicate: bool
    matched_session: ReturnSession | None


class ReturnBoxService:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        label: str,
        api_key: str,
        server_secret: str,
    ) -> ReturnBox:
        box = ReturnBox(
            id=new_uuid7(),
            label=label,
            api_key_hash=hash_device_key(api_key, server_secret),
            active=True,
            created_at=datetime.now(UTC),
        )
        session.add(box)
        await session.flush()
        return box

    @staticmethod
    async def authenticate(
        session: AsyncSession,
        *,
        return_box_id: uuid.UUID,
        api_key: str,
        server_secret: str,
    ) -> ReturnBox:
        box = (
            await session.execute(select(ReturnBox).where(ReturnBox.id == return_box_id))
        ).scalar_one_or_none()
        if box is None:
            raise HTTPException(status_code=404, detail="return box not found")
        if not box.active:
            raise HTTPException(status_code=403, detail="return box disabled")
        if box.api_key_hash != hash_device_key(api_key, server_secret):
            raise HTTPException(status_code=401, detail="invalid device key")
        return box


class SensorEventService:
    @staticmethod
    async def ingest(
        session: AsyncSession,
        *,
        return_box_id: uuid.UUID,
        device_event_id: str,
        event_type: str,
        triggered_at: datetime,
    ) -> IngestResult:
        existing = (
            await session.execute(
                select(SensorEvent).where(
                    SensorEvent.return_box_id == return_box_id,
                    SensorEvent.device_event_id == device_event_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            matched = None
            if existing.matched_return_session_id is not None:
                matched = (
                    await session.execute(
                        select(ReturnSession).where(
                            ReturnSession.id == existing.matched_return_session_id
                        )
                    )
                ).scalar_one_or_none()
            return IngestResult(sensor_event=existing, duplicate=True, matched_session=matched)

        now = datetime.now(UTC)
        active_session = (
            await session.execute(
                select(ReturnSession)
                .where(
                    ReturnSession.return_box_id == return_box_id,
                    ReturnSession.status == ReturnSessionStatus.SCANNED,
                    ReturnSession.expires_at > now,
                )
                .order_by(ReturnSession.scanned_at.desc())
                .limit(1)
                .with_for_update()
            )
        ).scalar_one_or_none()

        sensor_event = SensorEvent(
            id=new_uuid7(),
            return_box_id=return_box_id,
            device_event_id=device_event_id,
            event_type=event_type,
            matched_return_session_id=active_session.id if active_session else None,
            triggered_at=triggered_at,
            received_at=now,
        )
        session.add(sensor_event)

        if active_session is not None:
            asset = (
                await session.execute(
                    select(Asset).where(Asset.id == active_session.asset_id).with_for_update()
                )
            ).scalar_one()
            if asset.status == AssetStatus.RETURN_PENDING_DEPOSIT:
                assert_transition(
                    asset.status,
                    AssetStatus.DEPOSITED_IN_RETURN_BOX,
                    ActorRole.SYSTEM,
                )
                asset.status = AssetStatus.DEPOSITED_IN_RETURN_BOX
                asset.physical_holder_type = HolderType.RETURN_BOX
                asset.physical_holder_id = return_box_id
                session.add(asset)

                active_session.status = ReturnSessionStatus.DEPOSIT_DETECTED
                active_session.deposit_detected_at = now
                session.add(active_session)

                await HashChainService.append(
                    session,
                    asset_id=asset.id,
                    event_type=AssetEventType.RETURN_BOX_DEPOSIT_DETECTED,
                    actor_role=ActorRole.SYSTEM,
                    actor_id=return_box_id,
                    cycle_id=asset.current_cycle_id,
                    from_holder_type=HolderType.CONSUMER,
                    from_holder_id=active_session.scanned_by_consumer_id,
                    to_holder_type=HolderType.RETURN_BOX,
                    to_holder_id=return_box_id,
                    return_session_id=active_session.id,
                    occurred_at=now,
                    lock_asset=False,
                    metadata={"sensor_event_id": str(sensor_event.id)},
                )

        try:
            await session.flush()
        except IntegrityError as err:
            # Another concurrent ingest beat us; refetch and treat as duplicate.
            await session.rollback()
            row = (
                await session.execute(
                    select(SensorEvent).where(
                        SensorEvent.return_box_id == return_box_id,
                        SensorEvent.device_event_id == device_event_id,
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise HTTPException(status_code=500, detail="sensor ingest race") from err
            return IngestResult(sensor_event=row, duplicate=True, matched_session=None)

        return IngestResult(
            sensor_event=sensor_event,
            duplicate=False,
            matched_session=active_session,
        )
