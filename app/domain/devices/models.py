"""ReturnBox device + SensorEvent ingestion (D11/D13).

ReturnBox = physical drop-off device with HMAC-keyed API key.
SensorEvent = micro-switch trigger; idempotent on (return_box_id, device_event_id).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class ReturnBox(SQLModel, table=True):
    __tablename__ = "return_boxes"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    label: str = Field(sa_column=Column(String(128), nullable=False))
    api_key_hash: str = Field(sa_column=Column(String(64), unique=True, nullable=False))
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))


class SensorEvent(SQLModel, table=True):
    __tablename__ = "sensor_events"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    return_box_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    device_event_id: str = Field(sa_column=Column(String(128), nullable=False))
    event_type: str = Field(sa_column=Column(String(64), nullable=False))
    matched_return_session_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    triggered_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
    received_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        UniqueConstraint("return_box_id", "device_event_id", name="uq_sensor_events_box_device"),
        Index("ix_sensor_events_received", "received_at"),
    )
