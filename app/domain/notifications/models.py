"""Notification — return reminders + outcome notices (D13)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Index, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class NotificationChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    APP_PUSH = "app_push"


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class NotificationType(StrEnum):
    RETURN_REMINDER_DAY_7 = "return_reminder_day_7"
    RETURN_REMINDER_DAY_14 = "return_reminder_day_14"
    RETURN_REMINDER_DAY_21 = "return_reminder_day_21"
    RETURN_REMINDER_LAST_DAY = "return_reminder_last_day"
    DEPOSIT_CHARGED = "deposit_charged"
    DEPOSIT_RELEASED = "deposit_released"
    REWARD_GRANTED = "reward_granted"
    REWARD_EXPIRED = "reward_expired"
    RETURN_CONFIRMED = "return_confirmed"


def _enum_column(name: str, enum_cls: type[StrEnum], *, nullable: bool = False) -> Column[Any]:
    return Column(
        SAEnum(
            enum_cls,
            name=name,
            native_enum=True,
            validate_strings=True,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=nullable,
    )


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    consumer_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    deposit_record_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    channel: NotificationChannel = Field(
        sa_column=_enum_column("notification_channel", NotificationChannel)
    )
    notification_type: NotificationType = Field(
        sa_column=_enum_column("notification_type", NotificationType)
    )
    payload_summary: str | None = Field(default=None, sa_column=Column(String(256), nullable=True))
    scheduled_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    sent_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    status: NotificationStatus = Field(
        sa_column=_enum_column("notification_status", NotificationStatus)
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        UniqueConstraint(
            "deposit_record_id",
            "notification_type",
            name="uq_notifications_deposit_type",
        ),
        Index("ix_notifications_due", "status", "scheduled_at"),
        Index("ix_notifications_consumer", "consumer_id"),
    )
