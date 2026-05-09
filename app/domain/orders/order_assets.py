"""OrderAsset: assets bound to an order at pickup confirmation."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class OrderAsset(SQLModel, table=True):
    __tablename__ = "order_assets"

    order_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    asset_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    asset_type: str = Field(sa_column=Column(String(32), nullable=False))
    assigned_by_pickup_session_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), nullable=False)
    )
    picked_up_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    delivered_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )

    __table_args__ = (PrimaryKeyConstraint("order_id", "asset_id", name="pk_order_assets"),)
