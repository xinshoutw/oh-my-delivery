from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.assets.enums import AssetType
from app.domain.pickup.models import PickupSessionStatus


class CreatePickupSessionResponse(BaseModel):
    pickup_session_id: uuid.UUID
    order_id: uuid.UUID
    expected_manifest: dict[AssetType, int]
    expires_in_seconds: int
    expires_at: datetime
    status: PickupSessionStatus


class ScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_token: str | None = Field(default=None, max_length=64)
    short_code: str | None = Field(default=None, max_length=16)


class ProgressEntry(BaseModel):
    expected: int
    scanned: int


class ScanResponse(BaseModel):
    accepted: bool
    already_scanned: bool = False
    asset_id: uuid.UUID | None = None
    asset_type: AssetType | None = None
    asset_public_code: str | None = None
    reject_reason: str | None = None
    progress: dict[AssetType, ProgressEntry]
    fully_scanned: bool


class ConfirmedAssetItem(BaseModel):
    asset_id: uuid.UUID
    asset_type: AssetType
    public_code: str


class ConfirmPickupResponse(BaseModel):
    pickup_session_id: uuid.UUID
    order_id: uuid.UUID
    transferred_assets: list[ConfirmedAssetItem]
    order_status: str


class CancelPickupResponse(BaseModel):
    pickup_session_id: uuid.UUID
    status: PickupSessionStatus
