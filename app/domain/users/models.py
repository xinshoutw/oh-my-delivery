"""User stub for demo onboarding (admin / staff / courier / recycler).

Consumer 由 ``consumers`` 表覆蓋;Partner 由 ``partners`` 表覆蓋;本表收容剩餘角色。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class UserRole(StrEnum):
    ADMIN = "admin"
    CLEANING_STAFF = "cleaning_staff"
    RESTAURANT_STAFF = "restaurant_staff"
    COURIER = "courier"
    RECYCLER = "recycler"
    SUPPORT = "support"


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


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    role: UserRole = Field(sa_column=_enum_column("user_role", UserRole))
    organization_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    label: str = Field(sa_column=Column(String(128), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (
        Index("ix_users_role", "role"),
        Index("ix_users_organization", "organization_id"),
    )
