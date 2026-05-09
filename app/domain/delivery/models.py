"""DeliveryPinAttempt — every PIN attempt audited (D7)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class DeliveryPinAttempt(SQLModel, table=True):
    __tablename__ = "delivery_pin_attempts"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    order_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    courier_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    consumer_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    attempted_pin_hash: str = Field(sa_column=Column(String(64), nullable=False))
    success: bool = Field(sa_column=Column(Boolean, nullable=False))
    failed_reason: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    server_timestamp: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        Index("ix_delivery_pin_attempts_order", "order_id"),
        Index("ix_delivery_pin_attempts_order_success", "order_id", "success"),
    )
