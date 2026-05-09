"""Restaurant routes: receive-confirmation (one-button ack) and inventory."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_db_session, require_role
from app.domain.assets.enums import ActorRole
from app.domain.dispatches.schemas import AcknowledgeDispatchResponse
from app.domain.dispatches.service import DispatchService

router = APIRouter(prefix="/restaurant", tags=["restaurant"])


@router.post(
    "/dispatches/{dispatch_id}/acknowledge",
    response_model=AcknowledgeDispatchResponse,
)
async def acknowledge_dispatch(
    dispatch_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.RESTAURANT, ActorRole.ADMIN)),
) -> AcknowledgeDispatchResponse:
    if actor.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Organization-Id required for restaurant actor",
        )
    dispatch, asset_ids = await DispatchService.acknowledge_dispatch(
        session,
        dispatch_id=dispatch_id,
        restaurant_id=actor.organization_id,
        actor_id=actor.id,
    )
    return AcknowledgeDispatchResponse(
        dispatch_id=dispatch.id,
        acknowledged_count=len(asset_ids),
        asset_ids=asset_ids,
    )
