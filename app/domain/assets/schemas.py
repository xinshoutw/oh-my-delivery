"""Asset request / response schemas (Pydantic / SQLModel mixed)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.assets.enums import AssetStatus, AssetType, HolderType


class CreateAssetsRequest(BaseModel):
    asset_type: AssetType
    count: int = Field(ge=1, le=500)


class AssetCreatedItem(BaseModel):
    """One created asset — token is returned ONCE only (used to print QR)."""

    id: uuid.UUID
    asset_type: AssetType
    short_code: str
    asset_token: str
    status: AssetStatus


class CreateAssetsResponse(BaseModel):
    created: list[AssetCreatedItem]


class AssetSummary(BaseModel):
    id: uuid.UUID
    asset_type: AssetType
    short_code: str
    status: AssetStatus
    physical_holder_type: HolderType | None
    physical_holder_id: uuid.UUID | None
    responsible_party_type: HolderType | None
    responsible_party_id: uuid.UUID | None
    usage_count: int
    last_washed_at: datetime | None
    created_at: datetime
