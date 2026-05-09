"""Audit log writer.

Distinct from ``asset_events``: audit logs capture *human / admin / support*
operations with full before/after snapshots, while asset events capture the
asset's lifecycle.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_uuid7
from app.domain.audit.models import AuditLog


class AuditService:
    @staticmethod
    async def record(
        session: AsyncSession,
        *,
        actor_type: str,
        actor_id: uuid.UUID,
        action: str,
        target_type: str,
        target_id: uuid.UUID,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            id=new_uuid7(),
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            before_snapshot=before,
            after_snapshot=after,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=datetime.now(UTC),
        )
        session.add(log)
        await session.flush()
        return log
