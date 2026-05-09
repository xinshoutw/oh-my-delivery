from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.assets.enums import AssetType


class DeliverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pin: str = Field(min_length=4, max_length=8, pattern=r"^\d+$")


class DeliveredAssetItem(BaseModel):
    asset_id: uuid.UUID
    asset_type: AssetType
    deposit_id: uuid.UUID
    deposit_amount: int
    due_at: datetime
    reward_cutoff_at: datetime


class DeliverSuccessResponse(BaseModel):
    status: str = "delivered"
    order_id: uuid.UUID
    consumer_id: uuid.UUID
    delivered_assets: list[DeliveredAssetItem]
    consumer_wallet_balance_after: int


class DeliverFailedResponse(BaseModel):
    status: str  # pin_failed | pin_locked | pin_expired
    order_id: uuid.UUID
    remaining_attempts: int
    support_required: bool
    reason: str
