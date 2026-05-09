"""ChainAnchor — daily Merkle root over per-asset hash chain events (D13)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Column, Date, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class ChainAnchor(SQLModel, table=True):
    __tablename__ = "chain_anchors"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    anchor_date: date = Field(sa_column=Column(Date, nullable=False))
    root_hash: str = Field(sa_column=Column(String(64), nullable=False))
    event_count: int = Field(sa_column=Column(Integer, nullable=False))
    first_event_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    last_event_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (UniqueConstraint("anchor_date", name="uq_chain_anchors_date"),)
