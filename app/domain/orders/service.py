"""OrderService: Partner builds an order, system mints a one-time PIN."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.hashing import hash_pin
from app.core.ids import new_uuid7
from app.core.security import generate_pin
from app.domain.assets.enums import ActorRole, AssetType
from app.domain.audit.service import AuditService
from app.domain.consumers.service import ConsumerService
from app.domain.orders.models import Order, OrderStatus


class OrderService:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        partner_id: uuid.UUID,
        external_order_id: str,
        restaurant_id: uuid.UUID,
        courier_id: uuid.UUID,
        external_consumer_ref: str,
        expected_asset_manifest: dict[AssetType, int],
        consumer_email: str | None,
        consumer_phone: str | None,
        consumer_national_id_hash: str | None,
    ) -> tuple[Order, str]:
        if not expected_asset_manifest:
            raise HTTPException(status_code=400, detail="expected_asset_manifest must not be empty")
        if any(qty < 1 for qty in expected_asset_manifest.values()):
            raise HTTPException(status_code=400, detail="all manifest quantities must be >= 1")

        settings = get_settings()
        now = datetime.now(UTC)

        consumer = await ConsumerService.upsert_for_partner(
            session,
            partner_id=partner_id,
            external_ref=external_consumer_ref,
            national_id_hash=consumer_national_id_hash,
            email=consumer_email,
            phone=consumer_phone,
        )

        pin = generate_pin(6)
        pin_expires_at = now + timedelta(minutes=settings.pin_ttl_minutes)

        order = Order(
            id=new_uuid7(),
            partner_id=partner_id,
            external_order_id=external_order_id,
            restaurant_id=restaurant_id,
            consumer_id=consumer.id,
            courier_id=courier_id,
            status=OrderStatus.CREATED,
            expected_asset_manifest={k.value: v for k, v in expected_asset_manifest.items()},
            delivery_pin_hash=hash_pin(pin),
            delivery_pin_expires_at=pin_expires_at,
            pin_failed_count=0,
            created_at=now,
        )
        session.add(order)
        try:
            await session.flush()
        except IntegrityError as err:
            await session.rollback()
            raise HTTPException(
                status_code=409,
                detail=(
                    f"order already exists for partner / external_order_id {external_order_id}"
                ),
            ) from err

        await AuditService.record(
            session,
            actor_type=ActorRole.PARTNER.value,
            actor_id=partner_id,
            action="order.create",
            target_type="order",
            target_id=order.id,
            after={
                "external_order_id": external_order_id,
                "consumer_id": str(consumer.id),
                "manifest": order.expected_asset_manifest,
            },
        )
        return order, pin

    @staticmethod
    async def get_by_partner_and_external(
        session: AsyncSession,
        *,
        partner_id: uuid.UUID,
        external_order_id: str,
    ) -> Order | None:
        return (
            await session.execute(
                select(Order).where(
                    Order.partner_id == partner_id,
                    Order.external_order_id == external_order_id,
                )
            )
        ).scalar_one_or_none()
