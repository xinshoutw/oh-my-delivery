"""Dispatch + DispatchAsset: cleaning center ships a batch to a restaurant."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Index, PrimaryKeyConstraint, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class DispatchStatus(StrEnum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    CANCELLED = "cancelled"


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


class Dispatch(SQLModel, table=True):
    __tablename__ = "dispatches"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    cleaning_center_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    restaurant_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    status: DispatchStatus = Field(sa_column=_enum_column("dispatch_status", DispatchStatus))
    note: str | None = Field(default=None, sa_column=Column(String(256), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    acknowledged_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    acknowledged_by_actor_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )

    __table_args__ = (
        Index("ix_dispatches_restaurant_status", "restaurant_id", "status"),
        Index("ix_dispatches_cleaning_center", "cleaning_center_id"),
    )


class DispatchAsset(SQLModel, table=True):
    __tablename__ = "dispatch_assets"

    dispatch_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    asset_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))

    __table_args__ = (
        PrimaryKeyConstraint("dispatch_id", "asset_id", name="pk_dispatch_assets"),
        Index("ix_dispatch_assets_asset", "asset_id"),
    )
