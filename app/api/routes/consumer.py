"""Consumer routes: return scan + cancel."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_db_session, require_role
from app.domain.assets.enums import ActorRole
from app.domain.returns.schemas import (
    CancelReturnResponse,
    ConsumerReturnScanRequest,
    ConsumerReturnScanResponse,
)
from app.domain.returns.service import ReturnService

router = APIRouter(prefix="/consumer", tags=["consumer"])


@router.post("/returns/scan", response_model=ConsumerReturnScanResponse, status_code=201)
async def scan_for_return(
    body: ConsumerReturnScanRequest,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CONSUMER, ActorRole.ADMIN)),
) -> ConsumerReturnScanResponse:
    result = await ReturnService.scan(
        session,
        consumer_id=actor.id,
        return_box_id=body.return_box_id,
        asset_token=body.asset_token,
        short_code=body.short_code,
    )
    expires_in = max(
        0, int((result.session.expires_at - result.session.scanned_at).total_seconds())
    )
    msg = (
        "Please confirm the asset code, then drop it into the return box"
        if result.is_current_holder
        else (
            "This asset is held by another consumer; you may still help return "
            "it. Deposit and reward stay with the original holder."
        )
    )
    return ConsumerReturnScanResponse(
        return_session_id=result.session.id,
        asset_id=result.asset.id,
        asset_type=result.asset.asset_type,
        asset_public_code=result.asset.short_code,
        is_current_holder=result.is_current_holder,
        status=result.session.status,
        expires_in_seconds=expires_in,
        expires_at=result.session.expires_at,
        message=msg,
    )


@router.post(
    "/return-sessions/{return_session_id}/cancel",
    response_model=CancelReturnResponse,
)
async def cancel_return(
    return_session_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CONSUMER, ActorRole.ADMIN)),
) -> CancelReturnResponse:
    rs = await ReturnService.cancel(
        session,
        return_session_id=return_session_id,
        consumer_id=actor.id,
    )
    return CancelReturnResponse(return_session_id=rs.id, status=rs.status)
