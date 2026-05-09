from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.assets.enums import AssetType
from app.domain.returns.models import ReturnSessionStatus


class ConsumerReturnScanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_token: str | None = Field(default=None, max_length=64)
    short_code: str | None = Field(default=None, max_length=16)
    return_box_id: uuid.UUID


class ConsumerReturnScanResponse(BaseModel):
    return_session_id: uuid.UUID
    asset_id: uuid.UUID
    asset_type: AssetType
    asset_public_code: str
    is_current_holder: bool
    status: ReturnSessionStatus
    expires_in_seconds: int
    expires_at: datetime
    message: str


class CancelReturnResponse(BaseModel):
    return_session_id: uuid.UUID
    status: ReturnSessionStatus


class SensorEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_event_id: str = Field(min_length=1, max_length=128)
    event_type: str = Field(default="micro_switch_triggered", max_length=64)
    triggered_at: datetime


class SensorEventResponse(BaseModel):
    sensor_event_id: uuid.UUID
    duplicate: bool
    matched_return_session_id: uuid.UUID | None
    message: str
