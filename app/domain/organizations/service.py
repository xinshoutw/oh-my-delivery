"""OrganizationService: create + list."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_uuid7
from app.domain.organizations.models import Organization, OrganizationType


class OrganizationService:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        type_: OrganizationType,
        name: str,
    ) -> Organization:
        org = Organization(
            id=new_uuid7(),
            type=type_,
            name=name,
            created_at=datetime.now(UTC),
        )
        session.add(org)
        await session.flush()
        return org

    @staticmethod
    async def get(session: AsyncSession, org_id: uuid.UUID) -> Organization | None:
        return (
            await session.execute(select(Organization).where(Organization.id == org_id))
        ).scalar_one_or_none()

    @staticmethod
    async def list_all(
        session: AsyncSession,
        *,
        type_: OrganizationType | None = None,
    ) -> Sequence[Organization]:
        stmt = select(Organization).order_by(Organization.created_at.desc())
        if type_ is not None:
            stmt = stmt.where(Organization.type == type_)
        return list((await session.execute(stmt)).scalars().all())
