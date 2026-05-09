from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class ReceiveAssetsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_tokens: list[str] = Field(min_length=1, max_length=500)


class ReceivedAssetItem(BaseModel):
    asset_id: uuid.UUID
    asset_type: str
    deposit_outcome: str
    reward_granted: bool
    reward_points: int


class ReceiveAssetsResponse(BaseModel):
    received: list[ReceivedAssetItem]


class InspectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_id: uuid.UUID
    condition: str = Field(pattern=r"^(usable|damaged|retired)$")
    component_status: dict[str, str] | None = None
    notes: str | None = Field(default=None, max_length=512)


class InspectResponse(BaseModel):
    asset_id: uuid.UUID
    new_status: str


class CompleteWashingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    asset_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class CompleteWashingResponse(BaseModel):
    asset_ids: list[uuid.UUID]
    new_status: str = "cleaned_ready"
