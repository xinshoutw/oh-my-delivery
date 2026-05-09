"""DepositRecord (D5) — one row per (asset, cycle) deposit."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Index, Integer, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class DepositStatus(StrEnum):
    ACTIVE = "active"
    PENDING_RETURN_CONFIRMATION = "pending_return_confirmation"
    RELEASED = "released"
    CHARGED = "charged"
    WAIVED = "waived"
    DISPUTED = "disputed"


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


class DepositRecord(SQLModel, table=True):
    __tablename__ = "deposit_records"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    asset_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    consumer_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    order_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    cycle_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    amount: int = Field(sa_column=Column(Integer, nullable=False))
    status: DepositStatus = Field(sa_column=_enum_column("deposit_status", DepositStatus))
    borrowed_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    reward_cutoff_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    due_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    returned_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cleaning_confirmed_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    charged_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    released_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        UniqueConstraint("asset_id", "cycle_id", name="uq_deposit_asset_cycle"),
        Index("ix_deposit_consumer_status", "consumer_id", "status"),
        Index("ix_deposit_due_at", "due_at"),
    )
