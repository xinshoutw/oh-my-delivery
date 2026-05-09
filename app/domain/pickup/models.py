"""PickupScanSession + PickupScanItem (D10).

Scan stage buffers asset references; assets stay ``at_restaurant`` until the
courier confirms the session. On confirm, the entire batch transitions to
``picked_by_courier`` in one transaction so the order is never half-handed-off.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, Column, DateTime, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class PickupSessionStatus(StrEnum):
    ACTIVE = "active"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    FAILED = "failed"


class ScanMethod(StrEnum):
    QR_TOKEN = "qr_token"
    MANUAL_SHORT_CODE = "manual_short_code"


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


class PickupScanSession(SQLModel, table=True):
    __tablename__ = "pickup_scan_sessions"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    order_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    courier_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    restaurant_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    status: PickupSessionStatus = Field(
        sa_column=_enum_column("pickup_session_status", PickupSessionStatus)
    )
    expected_manifest: dict[str, int] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    confirmed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cancelled_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    __table_args__ = (
        Index("ix_pickup_sessions_order_status", "order_id", "status"),
        Index("ix_pickup_sessions_courier_status", "courier_id", "status"),
    )


class PickupScanItem(SQLModel, table=True):
    __tablename__ = "pickup_scan_items"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    session_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    asset_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    asset_type: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    scan_method: ScanMethod = Field(sa_column=_enum_column("scan_method", ScanMethod))
    scanned_code: str = Field(sa_column=Column(String(64), nullable=False))
    accepted: bool = Field(sa_column=Column(Boolean, nullable=False))
    reject_reason: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    scanned_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        Index("ix_pickup_scan_items_session", "session_id"),
        Index("ix_pickup_scan_items_session_asset", "session_id", "asset_id"),
    )
