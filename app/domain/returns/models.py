"""ReturnSession (D11) — consumer scan → micro-switch → cleaning center."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Index
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class ReturnSessionStatus(StrEnum):
    SCANNED = "scanned"
    DEPOSIT_DETECTED = "deposit_detected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    CONFIRMED_BY_CLEANING_CENTER = "confirmed_by_cleaning_center"


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


class ReturnSession(SQLModel, table=True):
    __tablename__ = "return_sessions"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    asset_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    scanned_by_consumer_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), nullable=False)
    )
    responsible_consumer_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    return_box_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    status: ReturnSessionStatus = Field(
        sa_column=_enum_column("return_session_status", ReturnSessionStatus)
    )
    scanned_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    deposit_detected_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cancelled_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cleaning_confirmed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        Index("ix_return_sessions_box_status", "return_box_id", "status"),
        Index("ix_return_sessions_asset_status", "asset_id", "status"),
    )
