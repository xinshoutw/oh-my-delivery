"""Return-box device routes: sensor event ingest with API-key auth."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.config import get_settings
from app.domain.devices.service import ReturnBoxService, SensorEventService
from app.domain.returns.schemas import SensorEventRequest, SensorEventResponse

router = APIRouter(prefix="/devices", tags=["devices"])


@router.post(
    "/return-boxes/{return_box_id}/sensor-events",
    response_model=SensorEventResponse,
    status_code=202,
)
async def ingest_sensor_event(
    return_box_id: uuid.UUID,
    body: SensorEventRequest,
    session: AsyncSession = Depends(get_db_session),
    x_device_key: str = Header(..., alias="X-Device-Key"),
) -> SensorEventResponse:
    settings = get_settings()
    await ReturnBoxService.authenticate(
        session,
        return_box_id=return_box_id,
        api_key=x_device_key,
        server_secret=settings.server_secret,
    )
    result = await SensorEventService.ingest(
        session,
        return_box_id=return_box_id,
        device_event_id=body.device_event_id,
        event_type=body.event_type,
        triggered_at=body.triggered_at,
    )
    if result.duplicate:
        msg = "duplicate device_event_id; ignored"
    elif result.deposit_recorded:
        msg = "matched return session; deposit recorded"
    elif result.matched_session is not None:
        msg = "session found but asset not in return_pending_deposit; no transition"
    else:
        msg = "orphan event recorded; no active return session"
    return SensorEventResponse(
        sensor_event_id=result.sensor_event.id,
        duplicate=result.duplicate,
        matched_return_session_id=result.matched_session.id if result.matched_session else None,
        deposit_recorded=result.deposit_recorded,
        message=msg,
    )
