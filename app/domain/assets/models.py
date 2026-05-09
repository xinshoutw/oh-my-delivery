"""Asset, AssetCycle, AssetEvent SQLModel tables."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Column, DateTime, Index, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlmodel import Field, SQLModel

from app.domain.assets.enums import (
    ActorRole,
    AssetStatus,
    AssetType,
    HolderType,
)


def _enum_column(
    enum_cls: type[StrEnum],
    name: str,
    *,
    nullable: bool = False,
    create_type: bool = True,
) -> Column[Any]:
    return Column(
        SAEnum(
            enum_cls,
            name=name,
            native_enum=True,
            validate_strings=True,
            create_type=create_type,
            values_callable=lambda enum: [member.value for member in enum],
        ),
        nullable=nullable,
    )


def _utc_dt_column(*, nullable: bool = False) -> Column[Any]:
    return Column(DateTime(timezone=True), nullable=nullable)


class CycleStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABORTED = "aborted"


class AssetEventType(StrEnum):
    ASSET_CREATED = "AssetCreated"
    ASSET_DISPATCHED_TO_RESTAURANT = "AssetDispatchedToRestaurant"
    ASSET_RECEIVED_BY_RESTAURANT = "AssetReceivedByRestaurant"
    PICKUP_SCAN_STARTED = "PickupScanStarted"
    ASSET_SCANNED_FOR_PICKUP = "AssetScannedForPickup"
    PICKUP_CONFIRMED_BY_COURIER = "PickupConfirmedByCourier"
    DELIVERY_PIN_FAILED = "DeliveryPinFailed"
    DELIVERY_PIN_VERIFIED = "DeliveryPinVerified"
    ASSET_DELIVERED_TO_CONSUMER = "AssetDeliveredToConsumer"
    CONSUMER_RETURN_SCANNED = "ConsumerReturnScanned"
    RETURN_BOX_DEPOSIT_DETECTED = "ReturnBoxDepositDetected"
    RETURN_BOX_COLLECTED = "ReturnBoxCollected"
    CLEANING_CENTER_RECEIVED = "CleaningCenterReceived"
    CLEANING_INSPECTION_STARTED = "CleaningInspectionStarted"
    CLEANING_INSPECTION_COMPLETED = "CleaningInspectionCompleted"
    WASHING_STARTED = "WashingStarted"
    WASHING_COMPLETED = "WashingCompleted"
    ASSET_MARKED_READY = "AssetMarkedReady"
    ASSET_MARKED_DAMAGED = "AssetMarkedDamaged"
    ASSET_MARKED_LOST = "AssetMarkedLost"
    ASSET_RETIRED = "AssetRetired"
    DEPOSIT_RELEASED = "DepositReleased"
    DEPOSIT_CHARGED = "DepositCharged"
    REWARD_GRANTED = "RewardGranted"
    SUPPORT_CASE_OPENED = "SupportCaseOpened"
    SUPPORT_CASE_RESOLVED = "SupportCaseResolved"


class Asset(SQLModel, table=True):
    __tablename__ = "assets"

    id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), primary_key=True),
    )
    asset_type: AssetType = Field(sa_column=_enum_column(AssetType, "asset_type"))
    short_code: str = Field(
        sa_column=Column(String(16), unique=True, nullable=False, index=True),
    )
    short_code_hash: str = Field(
        sa_column=Column(String(64), unique=True, nullable=False),
    )
    token_hash: str = Field(
        sa_column=Column(String(64), unique=True, nullable=False),
    )
    status: AssetStatus = Field(sa_column=_enum_column(AssetStatus, "asset_status"))
    physical_holder_type: HolderType | None = Field(
        default=None, sa_column=_enum_column(HolderType, "holder_type", nullable=True)
    )
    physical_holder_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    responsible_party_type: HolderType | None = Field(
        default=None,
        sa_column=_enum_column(HolderType, "holder_type", nullable=True, create_type=False),
    )
    responsible_party_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    current_cycle_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    usage_count: int = Field(default=0, nullable=False)
    last_washed_at: datetime | None = Field(default=None, sa_column=_utc_dt_column(nullable=True))
    created_at: datetime = Field(sa_column=_utc_dt_column())
    retired_at: datetime | None = Field(default=None, sa_column=_utc_dt_column(nullable=True))

    __table_args__ = (
        Index("ix_assets_status", "status"),
        Index("ix_assets_responsible_party", "responsible_party_type", "responsible_party_id"),
        Index("ix_assets_physical_holder", "physical_holder_type", "physical_holder_id"),
    )


class AssetCycle(SQLModel, table=True):
    __tablename__ = "asset_cycles"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    asset_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), nullable=False, index=True),
    )
    cycle_number: int = Field(nullable=False)
    started_at: datetime = Field(sa_column=_utc_dt_column())
    ended_at: datetime | None = Field(default=None, sa_column=_utc_dt_column(nullable=True))
    start_event_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    end_event_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    status: CycleStatus = Field(sa_column=_enum_column(CycleStatus, "cycle_status"))

    __table_args__ = (
        Index("uq_asset_cycles_asset_cycle", "asset_id", "cycle_number", unique=True),
    )


class AssetEvent(SQLModel, table=True):
    __tablename__ = "asset_events"

    id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), primary_key=True))
    asset_id: uuid.UUID = Field(
        sa_column=Column(PG_UUID(as_uuid=True), nullable=False, index=True),
    )
    cycle_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    event_type: AssetEventType = Field(sa_column=_enum_column(AssetEventType, "asset_event_type"))
    from_holder_type: HolderType | None = Field(
        default=None,
        sa_column=_enum_column(HolderType, "holder_type", nullable=True, create_type=False),
    )
    from_holder_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    to_holder_type: HolderType | None = Field(
        default=None,
        sa_column=_enum_column(HolderType, "holder_type", nullable=True, create_type=False),
    )
    to_holder_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    actor_role: ActorRole = Field(sa_column=_enum_column(ActorRole, "actor_role"))
    actor_id: uuid.UUID = Field(sa_column=Column(PG_UUID(as_uuid=True), nullable=False))
    order_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    pickup_session_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    return_session_id: uuid.UUID | None = Field(
        default=None, sa_column=Column(PG_UUID(as_uuid=True), nullable=True)
    )
    event_metadata: dict[str, Any] | None = Field(
        default=None, sa_column=Column("metadata", JSON, nullable=True)
    )
    previous_event_hash: str | None = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    event_hash: str = Field(sa_column=Column(String(64), nullable=False, unique=True))
    occurred_at: datetime = Field(sa_column=_utc_dt_column())
    created_at: datetime = Field(sa_column=_utc_dt_column())

    __table_args__ = (
        Index("ix_asset_events_asset_occurred", "asset_id", "occurred_at"),
        Index("ix_asset_events_event_type", "event_type"),
    )
