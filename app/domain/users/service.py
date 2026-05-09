"""UserService: create + list demo actor stubs."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_uuid7
from app.domain.users.models import User, UserRole


class UserService:
    @staticmethod
    async def create(
        session: AsyncSession,
        *,
        role: UserRole,
        label: str,
        organization_id: uuid.UUID | None = None,
    ) -> User:
        user = User(
            id=new_uuid7(),
            role=role,
            label=label,
            organization_id=organization_id,
            created_at=datetime.now(UTC),
        )
        session.add(user)
        await session.flush()
        return user

    @staticmethod
    async def list_all(
        session: AsyncSession,
        *,
        role: UserRole | None = None,
        organization_id: uuid.UUID | None = None,
    ) -> Sequence[User]:
        stmt = select(User).order_by(User.created_at.desc())
        if role is not None:
            stmt = stmt.where(User.role == role)
        if organization_id is not None:
            stmt = stmt.where(User.organization_id == organization_id)
        return list((await session.execute(stmt)).scalars().all())
