"""Cleaning-center routes: asset creation, dispatch, receive, inspection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_db_session, require_role
from app.domain.assets.enums import ActorRole
from app.domain.assets.schemas import CreateAssetsRequest, CreateAssetsResponse
from app.domain.assets.service import AssetService
from app.domain.dispatches.schemas import (
    CreateDispatchRequest,
    DispatchResponse,
    PrepareForDispatchRequest,
    PrepareForDispatchResponse,
)
from app.domain.dispatches.service import DispatchService

router = APIRouter(prefix="/cleaning", tags=["cleaning"])


def _require_org(actor: Actor) -> None:
    if actor.organization_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Organization-Id required",
        )


@router.post("/assets", response_model=CreateAssetsResponse, status_code=201)
async def create_assets(
    body: CreateAssetsRequest,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CLEANING_CENTER, ActorRole.ADMIN)),
) -> CreateAssetsResponse:
    _require_org(actor)
    assert actor.organization_id is not None
    created = await AssetService.create_assets(
        session,
        asset_type=body.asset_type,
        count=body.count,
        cleaning_center_id=actor.organization_id,
        actor_id=actor.id,
    )
    return CreateAssetsResponse(created=created)


@router.post("/assets/prepare-for-dispatch", response_model=PrepareForDispatchResponse)
async def prepare_for_dispatch(
    body: PrepareForDispatchRequest,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CLEANING_CENTER, ActorRole.ADMIN)),
) -> PrepareForDispatchResponse:
    _require_org(actor)
    assert actor.organization_id is not None
    asset_ids = await DispatchService.prepare_assets_for_dispatch(
        session,
        asset_ids=body.asset_ids,
        cleaning_center_id=actor.organization_id,
        actor_id=actor.id,
    )
    return PrepareForDispatchResponse(prepared_count=len(asset_ids), asset_ids=asset_ids)


@router.post("/dispatches", response_model=DispatchResponse, status_code=201)
async def create_dispatch(
    body: CreateDispatchRequest,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CLEANING_CENTER, ActorRole.ADMIN)),
) -> DispatchResponse:
    _require_org(actor)
    assert actor.organization_id is not None
    dispatch = await DispatchService.create_dispatch(
        session,
        cleaning_center_id=actor.organization_id,
        restaurant_id=body.restaurant_id,
        asset_ids=body.asset_ids,
        note=body.note,
        actor_id=actor.id,
    )
    return DispatchResponse(
        id=dispatch.id,
        cleaning_center_id=dispatch.cleaning_center_id,
        restaurant_id=dispatch.restaurant_id,
        status=dispatch.status,
        asset_ids=body.asset_ids,
        note=dispatch.note,
        created_at=dispatch.created_at,
        acknowledged_at=dispatch.acknowledged_at,
    )
