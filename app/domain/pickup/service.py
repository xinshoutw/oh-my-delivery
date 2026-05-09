"""PickupSessionService — courier scans each asset, confirms in one transaction.

Scope contract (D10):
* Scan stage never mutates Asset; the buffer lives in pickup_scan_items.
* Re-scanning the same token within an active session is idempotent (returns
  ``already_scanned=true``).
* Wrong restaurant / wrong type / over-quota / unknown token are recorded as
  rejected items so a courier app can show a useful error trail.
* Confirm runs all transitions inside the same SQL transaction; partial
  handoff is impossible.
"""

from __future__ import annotations

import uuid
from collections import Counter
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
    AssetType,
    HolderType,
)
from app.domain.assets.models import Asset, AssetEventType
from app.domain.assets.state_machine import assert_transition
from app.domain.audit.service import AuditService
from app.domain.hashchain.service import HashChainService
from app.domain.orders.models import Order, OrderStatus
from app.domain.orders.order_assets import OrderAsset
from app.domain.pickup.models import (
    PickupScanItem,
    PickupScanSession,
    PickupSessionStatus,
    ScanMethod,
)


class PickupSessionService:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        order_id: uuid.UUID,
        courier_id: uuid.UUID,
    ) -> PickupScanSession:
        order = await _load_order_for_courier(session, order_id, courier_id)
        if order.status not in {OrderStatus.CREATED}:
            raise HTTPException(
                status_code=409,
                detail=f"order is {order.status.value}; cannot start pickup",
            )

        active = (
            await session.execute(
                select(PickupScanSession).where(
                    PickupScanSession.order_id == order_id,
                    PickupScanSession.status == PickupSessionStatus.ACTIVE,
                )
            )
        ).scalar_one_or_none()
        if active is not None:
            return active

        settings = get_settings()
        now = datetime.now(UTC)
        pickup = PickupScanSession(
            id=new_uuid7(),
            order_id=order.id,
            courier_id=courier_id,
            restaurant_id=order.restaurant_id,
            status=PickupSessionStatus.ACTIVE,
            expected_manifest=dict(order.expected_asset_manifest),
            created_at=now,
            expires_at=now + timedelta(seconds=settings.pickup_session_ttl_seconds),
        )
        session.add(pickup)
        await session.flush()
        return pickup

    @staticmethod
    async def scan(
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        courier_id: uuid.UUID,
        asset_token: str | None,
        short_code: str | None,
    ) -> tuple[PickupScanSession, PickupScanItem, dict[AssetType, tuple[int, int]]]:
        if not asset_token and not short_code:
            raise HTTPException(status_code=400, detail="asset_token or short_code required")

        pickup = await _load_active_session(session, session_id, courier_id)
        settings = get_settings()
        now = datetime.now(UTC)
        scanned_code = (asset_token or short_code) or ""

        scan_method = ScanMethod.QR_TOKEN if asset_token else ScanMethod.MANUAL_SHORT_CODE
        asset = await _resolve_asset(session, asset_token=asset_token, short_code=short_code)

        if asset is None:
            return await _record_rejected_item(
                session,
                pickup=pickup,
                scan_method=scan_method,
                scanned_code=scanned_code,
                reject_reason="asset_not_found",
                now=now,
                expected=pickup.expected_manifest,
            )

        if (
            await session.execute(
                select(PickupScanItem).where(
                    PickupScanItem.session_id == pickup.id,
                    PickupScanItem.asset_id == asset.id,
                    PickupScanItem.accepted.is_(True),
                )
            )
        ).scalar_one_or_none() is not None:
            progress = await _build_progress(session, pickup)
            return (
                pickup,
                _ephemeral_already_scanned_item(asset, scan_method, scanned_code),
                progress,
            )

        if (
            asset.status != AssetStatus.AT_RESTAURANT
            or asset.physical_holder_id != pickup.restaurant_id
        ):
            return await _record_rejected_item(
                session,
                pickup=pickup,
                scan_method=scan_method,
                scanned_code=scanned_code,
                reject_reason="not_at_this_restaurant",
                now=now,
                expected=pickup.expected_manifest,
                asset_id=asset.id,
                asset_type=asset.asset_type.value,
            )

        manifest_qty = pickup.expected_manifest.get(asset.asset_type.value)
        if manifest_qty is None or manifest_qty < 1:
            return await _record_rejected_item(
                session,
                pickup=pickup,
                scan_method=scan_method,
                scanned_code=scanned_code,
                reject_reason="asset_type_not_in_manifest",
                now=now,
                expected=pickup.expected_manifest,
                asset_id=asset.id,
                asset_type=asset.asset_type.value,
            )

        scanned_for_type = await _count_accepted_for_type(
            session, pickup.id, asset.asset_type.value
        )
        if scanned_for_type >= manifest_qty:
            return await _record_rejected_item(
                session,
                pickup=pickup,
                scan_method=scan_method,
                scanned_code=scanned_code,
                reject_reason="manifest_quota_reached",
                now=now,
                expected=pickup.expected_manifest,
                asset_id=asset.id,
                asset_type=asset.asset_type.value,
            )

        item = PickupScanItem(
            id=new_uuid7(),
            session_id=pickup.id,
            asset_id=asset.id,
            asset_type=asset.asset_type.value,
            scan_method=scan_method,
            scanned_code=scanned_code[:64],
            accepted=True,
            reject_reason=None,
            scanned_at=now,
        )
        session.add(item)
        await session.flush()
        progress = await _build_progress(session, pickup)
        # Touch the courier role to keep the audit trail authentic.
        _ = settings  # silence unused; settings consulted earlier
        return pickup, item, progress

    @staticmethod
    async def confirm(
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        courier_id: uuid.UUID,
    ) -> tuple[PickupScanSession, list[Asset]]:
        pickup = await _load_active_session(session, session_id, courier_id)

        progress = await _build_progress(session, pickup)
        for asset_type, (expected, scanned) in progress.items():
            if scanned != expected:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"manifest incomplete: {asset_type.value} expected={expected} "
                        f"scanned={scanned}"
                    ),
                )

        accepted_asset_ids = [
            row[0]
            for row in (
                await session.execute(
                    select(PickupScanItem.asset_id).where(
                        PickupScanItem.session_id == pickup.id,
                        PickupScanItem.accepted.is_(True),
                    )
                )
            ).all()
            if row[0] is not None
        ]

        order = await _lock_order(session, pickup.order_id)
        if order.status != OrderStatus.CREATED:
            raise HTTPException(status_code=409, detail=f"order is {order.status.value}")

        assets_stmt = select(Asset).where(Asset.id.in_(accepted_asset_ids)).with_for_update()
        assets = list((await session.execute(assets_stmt)).scalars().all())
        now = datetime.now(UTC)

        for asset in assets:
            if asset.status != AssetStatus.AT_RESTAURANT:
                raise HTTPException(
                    status_code=409,
                    detail=f"asset {asset.id} no longer at_restaurant ({asset.status.value})",
                )
            assert_transition(asset.status, AssetStatus.PICKED_BY_COURIER, ActorRole.COURIER)
            asset.status = AssetStatus.PICKED_BY_COURIER
            asset.physical_holder_type = HolderType.COURIER
            asset.physical_holder_id = courier_id
            asset.responsible_party_type = HolderType.COURIER
            asset.responsible_party_id = courier_id
            session.add(asset)

            session.add(
                OrderAsset(
                    order_id=order.id,
                    asset_id=asset.id,
                    asset_type=asset.asset_type.value,
                    assigned_by_pickup_session_id=pickup.id,
                    picked_up_at=now,
                    delivered_at=None,
                )
            )

            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.PICKUP_CONFIRMED_BY_COURIER,
                actor_role=ActorRole.COURIER,
                actor_id=courier_id,
                cycle_id=asset.current_cycle_id,
                from_holder_type=HolderType.RESTAURANT,
                from_holder_id=pickup.restaurant_id,
                to_holder_type=HolderType.COURIER,
                to_holder_id=courier_id,
                order_id=order.id,
                pickup_session_id=pickup.id,
                occurred_at=now,
                lock_asset=False,
                metadata={"order_id": str(order.id)},
            )

        order.status = OrderStatus.PICKED_UP
        order.picked_up_at = now
        session.add(order)

        pickup.status = PickupSessionStatus.CONFIRMED
        pickup.confirmed_at = now
        session.add(pickup)

        await AuditService.record(
            session,
            actor_type=ActorRole.COURIER.value,
            actor_id=courier_id,
            action="pickup.confirm",
            target_type="order",
            target_id=order.id,
            after={
                "pickup_session_id": str(pickup.id),
                "asset_count": len(assets),
            },
        )
        await session.flush()
        return pickup, assets

    @staticmethod
    async def cancel(
        session: AsyncSession,
        *,
        session_id: uuid.UUID,
        courier_id: uuid.UUID,
    ) -> PickupScanSession:
        pickup = await _load_active_session(session, session_id, courier_id)
        pickup.status = PickupSessionStatus.CANCELLED
        pickup.cancelled_at = datetime.now(UTC)
        session.add(pickup)
        await session.flush()
        return pickup


async def _load_order_for_courier(
    session: AsyncSession,
    order_id: uuid.UUID,
    courier_id: uuid.UUID,
) -> Order:
    order = (await session.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    if order.courier_id != courier_id:
        raise HTTPException(status_code=403, detail="order not assigned to this courier")
    return order


async def _lock_order(session: AsyncSession, order_id: uuid.UUID) -> Order:
    order = (
        await session.execute(select(Order).where(Order.id == order_id).with_for_update())
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="order vanished")
    return order


async def _load_active_session(
    session: AsyncSession,
    session_id: uuid.UUID,
    courier_id: uuid.UUID,
) -> PickupScanSession:
    pickup = (
        await session.execute(
            select(PickupScanSession).where(PickupScanSession.id == session_id).with_for_update()
        )
    ).scalar_one_or_none()
    if pickup is None:
        raise HTTPException(status_code=404, detail="pickup session not found")
    if pickup.courier_id != courier_id:
        raise HTTPException(status_code=403, detail="pickup session belongs to another courier")
    if pickup.status != PickupSessionStatus.ACTIVE:
        raise HTTPException(
            status_code=409,
            detail=f"pickup session is {pickup.status.value}",
        )
    if pickup.expires_at <= datetime.now(UTC):
        pickup.status = PickupSessionStatus.EXPIRED
        session.add(pickup)
        raise HTTPException(status_code=410, detail="pickup session expired")
    return pickup


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


async def _record_rejected_item(
    session: AsyncSession,
    *,
    pickup: PickupScanSession,
    scan_method: ScanMethod,
    scanned_code: str,
    reject_reason: str,
    now: datetime,
    expected: dict[str, int],
    asset_id: uuid.UUID | None = None,
    asset_type: str | None = None,
) -> tuple[PickupScanSession, PickupScanItem, dict[AssetType, tuple[int, int]]]:
    item = PickupScanItem(
        id=new_uuid7(),
        session_id=pickup.id,
        asset_id=asset_id,
        asset_type=asset_type,
        scan_method=scan_method,
        scanned_code=scanned_code[:64],
        accepted=False,
        reject_reason=reject_reason,
        scanned_at=now,
    )
    session.add(item)
    await session.flush()
    progress = await _build_progress(session, pickup)
    _ = expected
    return pickup, item, progress


async def _count_accepted_for_type(
    session: AsyncSession, session_id: uuid.UUID, asset_type: str
) -> int:
    rows = (
        (
            await session.execute(
                select(PickupScanItem).where(
                    PickupScanItem.session_id == session_id,
                    PickupScanItem.accepted.is_(True),
                    PickupScanItem.asset_type == asset_type,
                )
            )
        )
        .scalars()
        .all()
    )
    return len(rows)


async def _build_progress(
    session: AsyncSession, pickup: PickupScanSession
) -> dict[AssetType, tuple[int, int]]:
    rows = (
        await session.execute(
            select(PickupScanItem.asset_type).where(
                PickupScanItem.session_id == pickup.id,
                PickupScanItem.accepted.is_(True),
            )
        )
    ).all()
    counts = Counter(row[0] for row in rows if row[0] is not None)
    progress: dict[AssetType, tuple[int, int]] = {}
    for asset_type_str, expected_qty in pickup.expected_manifest.items():
        try:
            asset_type = AssetType(asset_type_str)
        except ValueError:
            continue
        progress[asset_type] = (expected_qty, counts.get(asset_type_str, 0))
    return progress


def _ephemeral_already_scanned_item(
    asset: Asset, scan_method: ScanMethod, scanned_code: str
) -> PickupScanItem:
    """Returned to API layer for "already scanned" responses; never persisted."""
    return PickupScanItem(
        id=new_uuid7(),
        session_id=new_uuid7(),  # unused — caller doesn't read this
        asset_id=asset.id,
        asset_type=asset.asset_type.value,
        scan_method=scan_method,
        scanned_code=scanned_code[:64],
        accepted=False,
        reject_reason="already_scanned",
        scanned_at=datetime.now(UTC),
    )
