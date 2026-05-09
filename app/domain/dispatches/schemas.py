from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.domain.dispatches.models import DispatchStatus


class PrepareForDispatchRequest(BaseModel):
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class PrepareForDispatchResponse(BaseModel):
    prepared_count: int
    asset_ids: list[uuid.UUID]


class CreateDispatchRequest(BaseModel):
    restaurant_id: uuid.UUID
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    note: str | None = Field(default=None, max_length=256)


class DispatchResponse(BaseModel):
    id: uuid.UUID
    cleaning_center_id: uuid.UUID
    restaurant_id: uuid.UUID
    status: DispatchStatus
    asset_ids: list[uuid.UUID]
    note: str | None
    created_at: datetime
    acknowledged_at: datetime | None


class AcknowledgeDispatchResponse(BaseModel):
    dispatch_id: uuid.UUID
    acknowledged_count: int
    asset_ids: list[uuid.UUID]
