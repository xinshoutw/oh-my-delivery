"""Partner: outside delivery platform integrating with our system."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class Partner(SQLModel, table=True):
    __tablename__ = "partners"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    name: str = Field(sa_column=Column(String(128), nullable=False))
    api_key_hash: str = Field(sa_column=Column(String(64), unique=True, nullable=False))
    active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, default=True))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))
