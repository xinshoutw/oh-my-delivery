"""WashingBatch + WashingBatchItem — operational records, component_status JSONB."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class WashingBatchStatus(StrEnum):
    CREATED = "created"
    WASHING = "washing"
    COMPLETED = "completed"
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


class WashingBatch(SQLModel, table=True):
    __tablename__ = "washing_batches"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    cleaning_center_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    operator_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    status: WashingBatchStatus = Field(
        sa_column=_enum_column("washing_batch_status", WashingBatchStatus)
    )
    started_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    finished_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class WashingBatchItem(SQLModel, table=True):
    __tablename__ = "washing_batch_items"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    batch_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    asset_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    pre_check_status: str = Field(sa_column=Column(String(32), nullable=False))
    post_check_status: str | None = Field(default=None, sa_column=Column(String(32), nullable=True))
    component_status: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    notes: str | None = Field(default=None, sa_column=Column(String(512), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        Index("ix_washing_items_batch", "batch_id"),
        Index("ix_washing_items_asset", "asset_id"),
    )
