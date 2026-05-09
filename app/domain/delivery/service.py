"""DeliveryService: courier verifies PIN, system transfers assets to consumer.

Atomicity contract (D7):
* Every PIN attempt is recorded in ``delivery_pin_attempts`` regardless of
  outcome.
* ``order.pin_failed_count`` is the source of truth for lockout; threshold
  = ``settings.pin_max_attempts``.
* On success, asset transitions, deposit creation, wallet freeze, hash
  chain events, and order status update all share a single SQL transaction.
* On success the stored ``delivery_pin_hash`` is cleared so a replay can
  never succeed even if the row leaks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.hashing import hash_pin
from app.core.ids import new_uuid7
from app.domain.assets.enums import (
    ActorRole,
    AssetStatus,
    HolderType,
)
from app.domain.assets.models import Asset, AssetEventType
from app.domain.assets.state_machine import assert_transition
from app.domain.audit.service import AuditService
from app.domain.consumers.models import Consumer
from app.domain.delivery.models import DeliveryPinAttempt
from app.domain.deposits.models import DepositRecord, DepositStatus
from app.domain.hashchain.service import HashChainService
from app.domain.notifications.service import NotificationService
from app.domain.orders.models import Order, OrderStatus
from app.domain.orders.order_assets import OrderAsset


@dataclass(frozen=True)
class DeliveryFailure:
    reason: str
    remaining_attempts: int
    support_required: bool


@dataclass(frozen=True)
class DeliveredDeposit:
    asset_id: uuid.UUID
    asset_type: str
    deposit_id: uuid.UUID
    amount: int
    due_at: datetime
    reward_cutoff_at: datetime


@dataclass(frozen=True)
class DeliverySuccess:
    order_id: uuid.UUID
    consumer_id: uuid.UUID
    deposits: list[DeliveredDeposit]
    consumer_wallet_balance_after: int


class DeliveryService:
    @staticmethod
    async def deliver(
        session: AsyncSession,
        *,
        order_id: uuid.UUID,
        courier_id: uuid.UUID,
        pin: str,
    ) -> DeliverySuccess | DeliveryFailure:
        settings = get_settings()
        order = await _lock_order(session, order_id)

        if order.courier_id != courier_id:
            raise HTTPException(status_code=403, detail="order not assigned to this courier")

        if order.status == OrderStatus.PIN_LOCKED:
            return DeliveryFailure(reason="pin_locked", remaining_attempts=0, support_required=True)
        if order.status != OrderStatus.PICKED_UP:
            raise HTTPException(
                status_code=409,
                detail=f"order is {order.status.value}; cannot deliver",
            )

        attempted_hash = hash_pin(pin)
        now = datetime.now(UTC)

        if order.delivery_pin_expires_at and order.delivery_pin_expires_at < now:
            await _record_pin_attempt(
                session,
                order=order,
                courier_id=courier_id,
                attempted_pin_hash=attempted_hash,
                success=False,
                failed_reason="pin_expired",
                now=now,
            )
            return DeliveryFailure(
                reason="pin_expired",
                remaining_attempts=0,
                support_required=True,
            )

        if order.delivery_pin_hash != attempted_hash:
            order.pin_failed_count += 1
            session.add(order)
            await _record_pin_attempt(
                session,
                order=order,
                courier_id=courier_id,
                attempted_pin_hash=attempted_hash,
                success=False,
                failed_reason="wrong_pin",
                now=now,
            )
            if order.pin_failed_count >= settings.pin_max_attempts:
                order.status = OrderStatus.PIN_LOCKED
                session.add(order)
                await AuditService.record(
                    session,
                    actor_type=ActorRole.SYSTEM.value,
                    actor_id=courier_id,
                    action="order.pin_locked",
                    target_type="order",
                    target_id=order.id,
                    after={"pin_failed_count": order.pin_failed_count},
                )
                return DeliveryFailure(
                    reason="pin_locked",
                    remaining_attempts=0,
                    support_required=True,
                )
            remaining = settings.pin_max_attempts - order.pin_failed_count
            return DeliveryFailure(
                reason="wrong_pin",
                remaining_attempts=remaining,
                support_required=False,
            )

        success = await _commit_delivery(
            session,
            order=order,
            courier_id=courier_id,
            attempted_hash=attempted_hash,
            settings=settings,
            now=now,
        )
        return success


async def _lock_order(session: AsyncSession, order_id: uuid.UUID) -> Order:
    order = (
        await session.execute(select(Order).where(Order.id == order_id).with_for_update())
    ).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    return order


async def _record_pin_attempt(
    session: AsyncSession,
    *,
    order: Order,
    courier_id: uuid.UUID,
    attempted_pin_hash: str,
    success: bool,
    failed_reason: str | None,
    now: datetime,
) -> DeliveryPinAttempt:
    attempt = DeliveryPinAttempt(
        id=new_uuid7(),
        order_id=order.id,
        courier_id=courier_id,
        consumer_id=order.consumer_id,
        attempted_pin_hash=attempted_pin_hash,
        success=success,
        failed_reason=failed_reason,
        server_timestamp=now,
        created_at=now,
    )
    session.add(attempt)
    await session.flush()
    return attempt


async def _commit_delivery(
    session: AsyncSession,
    *,
    order: Order,
    courier_id: uuid.UUID,
    attempted_hash: str,
    settings: Settings,
    now: datetime,
) -> DeliverySuccess:
    consumer = (
        await session.execute(
            select(Consumer).where(Consumer.id == order.consumer_id).with_for_update()
        )
    ).scalar_one()

    order_asset_rows = (
        (await session.execute(select(OrderAsset).where(OrderAsset.order_id == order.id)))
        .scalars()
        .all()
    )
    if not order_asset_rows:
        raise HTTPException(status_code=409, detail="order has no order_assets")

    asset_ids = [row.asset_id for row in order_asset_rows]
    assets = list(
        (await session.execute(select(Asset).where(Asset.id.in_(asset_ids)).with_for_update()))
        .scalars()
        .all()
    )

    deposit_amount = consumer.current_required_deposit
    reward_cutoff_at = now + timedelta(days=settings.reward_window_days)
    due_at = now + timedelta(days=settings.deposit_due_days)
    deposits: list[DeliveredDeposit] = []

    for asset in assets:
        if asset.status != AssetStatus.PICKED_BY_COURIER:
            raise HTTPException(
                status_code=409,
                detail=f"asset {asset.id} not picked_by_courier ({asset.status.value})",
            )
        if asset.current_cycle_id is None:
            raise HTTPException(
                status_code=500,
                detail=f"asset {asset.id} missing current_cycle_id",
            )

        assert_transition(asset.status, AssetStatus.WITH_CONSUMER, ActorRole.COURIER)
        asset.status = AssetStatus.WITH_CONSUMER
        asset.physical_holder_type = HolderType.CONSUMER
        asset.physical_holder_id = consumer.id
        asset.responsible_party_type = HolderType.CONSUMER
        asset.responsible_party_id = consumer.id
        session.add(asset)

        deposit = DepositRecord(
            id=new_uuid7(),
            asset_id=asset.id,
            consumer_id=consumer.id,
            order_id=order.id,
            cycle_id=asset.current_cycle_id,
            amount=deposit_amount,
            status=DepositStatus.ACTIVE,
            borrowed_at=now,
            reward_cutoff_at=reward_cutoff_at,
            due_at=due_at,
            created_at=now,
        )
        session.add(deposit)
        await session.flush()
        await NotificationService.schedule_for_deposit(session, deposit)

        consumer.wallet_balance -= deposit_amount

        for ev in (
            AssetEventType.DELIVERY_PIN_VERIFIED,
            AssetEventType.ASSET_DELIVERED_TO_CONSUMER,
        ):
            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=ev,
                actor_role=ActorRole.COURIER,
                actor_id=courier_id,
                cycle_id=asset.current_cycle_id,
                from_holder_type=HolderType.COURIER,
                from_holder_id=courier_id,
                to_holder_type=HolderType.CONSUMER,
                to_holder_id=consumer.id,
                order_id=order.id,
                occurred_at=now,
                lock_asset=False,
                metadata={"order_id": str(order.id)},
            )

        for row in order_asset_rows:
            if row.asset_id == asset.id:
                row.delivered_at = now
                session.add(row)

        deposits.append(
            DeliveredDeposit(
                asset_id=asset.id,
                asset_type=asset.asset_type.value,
                deposit_id=deposit.id,
                amount=deposit_amount,
                due_at=due_at,
                reward_cutoff_at=reward_cutoff_at,
            )
        )

    session.add(consumer)

    order.status = OrderStatus.DELIVERED
    order.delivered_at = now
    order.delivery_pin_hash = None
    order.delivery_pin_expires_at = None
    session.add(order)

    await _record_pin_attempt(
        session,
        order=order,
        courier_id=courier_id,
        attempted_pin_hash=attempted_hash,
        success=True,
        failed_reason=None,
        now=now,
    )

    await AuditService.record(
        session,
        actor_type=ActorRole.COURIER.value,
        actor_id=courier_id,
        action="order.deliver",
        target_type="order",
        target_id=order.id,
        after={
            "consumer_id": str(consumer.id),
            "asset_count": len(assets),
            "deposit_total": deposit_amount * len(assets),
            "wallet_balance_after": consumer.wallet_balance,
        },
    )
    return DeliverySuccess(
        order_id=order.id,
        consumer_id=consumer.id,
        deposits=deposits,
        consumer_wallet_balance_after=consumer.wallet_balance,
    )
