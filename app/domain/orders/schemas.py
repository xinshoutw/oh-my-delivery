from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.assets.enums import AssetType
from app.domain.orders.models import OrderStatus


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_order_id: str = Field(min_length=1, max_length=128)
    restaurant_id: uuid.UUID
    courier_id: uuid.UUID
    external_consumer_ref: str = Field(min_length=1, max_length=128)
    expected_asset_manifest: dict[AssetType, int] = Field(
        ..., description="e.g. {'meal_box': 1, 'drink_cup': 2}"
    )
    consumer_email: str | None = Field(default=None, max_length=256)
    consumer_phone: str | None = Field(default=None, max_length=32)
    consumer_national_id_hash: str | None = Field(default=None, max_length=64)


class CreateOrderResponse(BaseModel):
    order_id: uuid.UUID
    external_order_id: str
    consumer_id: uuid.UUID
    status: OrderStatus
    delivery_pin: str  # one-time, returned only on creation
    delivery_pin_expires_at: datetime
    expected_asset_manifest: dict[AssetType, int]
    created_at: datetime
