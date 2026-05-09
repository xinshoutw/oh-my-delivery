"""PartnerService: API key hashing + lookup."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.hashing import hmac_sha256_hex
from app.core.ids import new_uuid7
from app.domain.partners.models import Partner


def hash_api_key(api_key: str, server_secret: str) -> str:
    return hmac_sha256_hex(api_key, server_secret)


class PartnerService:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        name: str,
        api_key: str,
        server_secret: str,
    ) -> Partner:
        partner = Partner(
            id=new_uuid7(),
            name=name,
            api_key_hash=hash_api_key(api_key, server_secret),
            active=True,
            created_at=datetime.now(UTC),
        )
        session.add(partner)
        await session.flush()
        return partner

    @staticmethod
    async def find_by_api_key(
        session: AsyncSession, *, api_key: str, server_secret: str
    ) -> Partner | None:
        api_key_hash = hash_api_key(api_key, server_secret)
        result = await session.execute(
            select(Partner).where(
                Partner.api_key_hash == api_key_hash,
                Partner.active.is_(True),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get(session: AsyncSession, partner_id: uuid.UUID) -> Partner | None:
        return (
            await session.execute(select(Partner).where(Partner.id == partner_id))
        ).scalar_one_or_none()
