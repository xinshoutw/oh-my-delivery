"""NotificationService — schedule reminders + dispatch due notifications.

Demo behavior: dispatch only marks the row sent + appends a structured log
line. No real email/SMS provider is wired up.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_uuid7
from app.domain.deposits.models import DepositRecord
from app.domain.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)

_logger = logging.getLogger("omd.notifications")


_REMINDER_OFFSETS = (
    (NotificationType.RETURN_REMINDER_DAY_7, timedelta(days=7)),
    (NotificationType.RETURN_REMINDER_DAY_14, timedelta(days=14)),
    (NotificationType.RETURN_REMINDER_DAY_21, timedelta(days=21)),
    (NotificationType.RETURN_REMINDER_LAST_DAY, timedelta(days=30)),
)


class NotificationService:
    @staticmethod
    async def schedule_for_deposit(
        session: AsyncSession,
        deposit: DepositRecord,
        *,
        channel: NotificationChannel = NotificationChannel.APP_PUSH,
    ) -> int:
        """Insert one Notification row per reminder type for a fresh deposit.

        Idempotent: UNIQUE(deposit_record_id, notification_type) absorbs reruns.
        Returns the number of new rows actually inserted.
        """
        now = datetime.now(UTC)
        inserted = 0
        for ntype, offset in _REMINDER_OFFSETS:
            scheduled_at = deposit.borrowed_at + offset
            if scheduled_at <= now:
                continue
            note = Notification(
                id=new_uuid7(),
                consumer_id=deposit.consumer_id,
                deposit_record_id=deposit.id,
                channel=channel,
                notification_type=ntype,
                payload_summary=(f"return_by={deposit.due_at.isoformat()};amount={deposit.amount}"),
                scheduled_at=scheduled_at,
                sent_at=None,
                status=NotificationStatus.PENDING,
                created_at=now,
            )
            session.add(note)
            try:
                await session.flush()
                inserted += 1
            except IntegrityError:
                await session.rollback()
        return inserted

    @staticmethod
    async def dispatch_due(
        session: AsyncSession,
        *,
        as_of: datetime | None = None,
        limit: int = 100,
    ) -> int:
        as_of = as_of or datetime.now(UTC)
        rows = (
            (
                await session.execute(
                    select(Notification)
                    .where(
                        Notification.status == NotificationStatus.PENDING,
                        Notification.scheduled_at <= as_of,
                    )
                    .order_by(Notification.scheduled_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        sent = 0
        for note in rows:
            note.status = NotificationStatus.SENT
            note.sent_at = as_of
            session.add(note)
            _logger.info(
                "notification dispatched id=%s type=%s consumer=%s payload=%s",
                note.id,
                note.notification_type.value,
                note.consumer_id,
                note.payload_summary,
            )
            sent += 1
        await session.flush()
        return sent

    @staticmethod
    async def cancel_for_deposit(
        session: AsyncSession,
        *,
        deposit_record_id: uuid.UUID,
        types: tuple[NotificationType, ...] | None = None,
    ) -> int:
        stmt = select(Notification).where(
            Notification.deposit_record_id == deposit_record_id,
            Notification.status == NotificationStatus.PENDING,
        )
        if types is not None:
            stmt = stmt.where(Notification.notification_type.in_(types))
        rows = (await session.execute(stmt)).scalars().all()
        cancelled = 0
        for note in rows:
            note.status = NotificationStatus.CANCELLED
            session.add(note)
            cancelled += 1
        await session.flush()
        return cancelled
