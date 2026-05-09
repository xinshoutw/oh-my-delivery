"""ConsumerService: upsert consumers via partner external refs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.ids import new_uuid7
from app.domain.consumers.models import Consumer, PartnerConsumer


class ConsumerService:
    @staticmethod
    async def upsert_for_partner(
        session: AsyncSession,
        *,
        partner_id: uuid.UUID,
        external_ref: str,
        national_id_hash: str | None = None,
        email: str | None = None,
        phone: str | None = None,
    ) -> Consumer:
        """Find consumer by (partner, external_ref); else by national_id_hash; else create.

        Lookup order matches D3:

        1. ``partner_consumers`` row → existing consumer
        2. ``national_id_hash`` match → join existing consumer to this partner
        3. New consumer + new partner-consumer mapping
        """
        settings = get_settings()
        now = datetime.now(UTC)

        existing_link = (
            await session.execute(
                select(PartnerConsumer).where(
                    PartnerConsumer.partner_id == partner_id,
                    PartnerConsumer.external_ref == external_ref,
                )
            )
        ).scalar_one_or_none()
        if existing_link is not None:
            return (
                await session.execute(
                    select(Consumer).where(Consumer.id == existing_link.consumer_id)
                )
            ).scalar_one()

        if national_id_hash:
            consumer = (
                await session.execute(
                    select(Consumer).where(Consumer.national_id_hash == national_id_hash)
                )
            ).scalar_one_or_none()
            if consumer is not None:
                session.add(
                    PartnerConsumer(
                        partner_id=partner_id,
                        external_ref=external_ref,
                        consumer_id=consumer.id,
                        created_at=now,
                    )
                )
                _patch_contact_info(consumer, email=email, phone=phone)
                return consumer

        consumer = Consumer(
            id=new_uuid7(),
            national_id_hash=national_id_hash,
            email=email,
            phone=phone,
            deposit_level=0,
            current_required_deposit=settings.deposit_base_amount,
            overdue_count=0,
            wallet_balance=settings.deposit_base_amount * 5,  # demo: pre-funded for trial
            points=0,
            last_overdue_at=None,
            created_at=now,
        )
        session.add(consumer)
        session.add(
            PartnerConsumer(
                partner_id=partner_id,
                external_ref=external_ref,
                consumer_id=consumer.id,
                created_at=now,
            )
        )
        await session.flush()
        return consumer


def _patch_contact_info(consumer: Consumer, *, email: str | None, phone: str | None) -> None:
    if email and not consumer.email:
        consumer.email = email
    if phone and not consumer.phone:
        consumer.phone = phone
