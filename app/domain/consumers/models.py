"""Consumer + Partner-Consumer mapping (D3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Index, Integer, PrimaryKeyConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class Consumer(SQLModel, table=True):
    __tablename__ = "consumers"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    national_id_hash: str | None = Field(
        default=None,
        sa_column=Column(String(64), unique=True, nullable=True),
    )
    email: str | None = Field(default=None, sa_column=Column(String(256), nullable=True))
    phone: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))

    deposit_level: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    current_required_deposit: int = Field(
        default=200, sa_column=Column(Integer, nullable=False, default=200)
    )
    overdue_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))

    wallet_balance: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    points: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))

    last_overdue_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class PartnerConsumer(SQLModel, table=True):
    __tablename__ = "partner_consumers"

    partner_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    external_ref: str = Field(sa_column=Column(String(128), nullable=False))
    consumer_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        PrimaryKeyConstraint("partner_id", "external_ref", name="pk_partner_consumers"),
        Index("ix_partner_consumers_consumer", "consumer_id"),
    )
