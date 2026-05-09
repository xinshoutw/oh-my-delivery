"""Audit log: human / admin / support operations on the system."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    actor_type: str = Field(sa_column=Column(String(32), nullable=False))
    actor_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    action: str = Field(sa_column=Column(String(64), nullable=False))
    target_type: str = Field(sa_column=Column(String(32), nullable=False))
    target_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    before_snapshot: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    after_snapshot: dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    ip_address: str | None = Field(default=None, sa_column=Column(String(64), nullable=True))
    user_agent: str | None = Field(default=None, sa_column=Column(String(256), nullable=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        Index("ix_audit_logs_target", "target_type", "target_id"),
        Index("ix_audit_logs_actor", "actor_type", "actor_id"),
        Index("ix_audit_logs_created_at", "created_at"),
    )
