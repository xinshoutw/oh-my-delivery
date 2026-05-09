"""Organization (cleaning_center / restaurant) — for demo onboarding."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel


class OrganizationType(StrEnum):
    CLEANING_CENTER = "cleaning_center"
    RESTAURANT = "restaurant"


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


class Organization(SQLModel, table=True):
    __tablename__ = "organizations"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    type: OrganizationType = Field(sa_column=_enum_column("organization_type", OrganizationType))
    name: str = Field(sa_column=Column(String(128), nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False))

    __table_args__ = (Index("ix_organizations_type", "type"),)
