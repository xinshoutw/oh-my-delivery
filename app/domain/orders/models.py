"""Order: delivery order (one external_order from a Partner platform)."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class OrderStatus(StrEnum):
    CREATED = "created"
    PICKED_UP = "picked_up"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    PIN_LOCKED = "pin_locked"


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


class Order(SQLModel, table=True):
    __tablename__ = "orders"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    partner_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    external_order_id: str = Field(sa_column=Column(String(128), nullable=False))
    restaurant_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    consumer_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    courier_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    status: OrderStatus = Field(sa_column=_enum_column("order_status", OrderStatus))
    expected_asset_manifest: dict[str, int] = Field(
        sa_column=Column(JSON, nullable=False),
    )
    delivery_pin_hash: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    delivery_pin_expires_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    pin_failed_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    picked_up_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    delivered_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    __table_args__ = (
        UniqueConstraint("partner_id", "external_order_id", name="uq_orders_partner_external"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_consumer", "consumer_id"),
        Index("ix_orders_courier_status", "courier_id", "status"),
        Index("ix_orders_restaurant_status", "restaurant_id", "status"),
    )
