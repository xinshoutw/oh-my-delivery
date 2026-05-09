"""FastAPI dependencies: DB session, authenticated actor.

Auth is intentionally stub-shaped for the demo: the actor's role and id are
read from request headers ``X-Role`` and ``X-Actor-Id``. JWT-based auth will
replace this once the user-management slice lands.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.domain.assets.enums import ActorRole


@dataclass(frozen=True)
class Actor:
    role: ActorRole
    id: uuid.UUID
    organization_id: uuid.UUID | None = None


async def get_db_session() -> AsyncIterator[AsyncSession]:
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_actor(
    x_role: str = Header(..., alias="X-Role"),
    x_actor_id: str = Header(..., alias="X-Actor-Id"),
    x_organization_id: str | None = Header(None, alias="X-Organization-Id"),
) -> Actor:
    try:
        role = ActorRole(x_role)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"unknown role: {x_role}",
        ) from err
    try:
        actor_id = uuid.UUID(x_actor_id)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid X-Actor-Id",
        ) from err
    org_id = uuid.UUID(x_organization_id) if x_organization_id else None
    return Actor(role=role, id=actor_id, organization_id=org_id)


def require_role(*allowed: ActorRole):
    allowed_set = frozenset(allowed)

    async def _dep(actor: Actor = Depends(get_actor)) -> Actor:
        if actor.role not in allowed_set:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role {actor.role} not allowed",
            )
        return actor

    return _dep
