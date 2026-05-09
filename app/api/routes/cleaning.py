"""Cleaning-center routes: asset creation, dispatch, receive, inspection."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_db_session, require_role
from app.domain.assets.enums import ActorRole
from app.domain.assets.schemas import CreateAssetsRequest, CreateAssetsResponse
from app.domain.assets.service import AssetService

router = APIRouter(prefix="/cleaning", tags=["cleaning"])


@router.post("/assets", response_model=CreateAssetsResponse, status_code=201)
async def create_assets(
    body: CreateAssetsRequest,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CLEANING_CENTER, ActorRole.ADMIN)),
) -> CreateAssetsResponse:
    if actor.organization_id is None:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Organization-Id required for cleaning_center actor",
        )
    created = await AssetService.create_assets(
        session,
        asset_type=body.asset_type,
        count=body.count,
        cleaning_center_id=actor.organization_id,
        actor_id=actor.id,
    )
    return CreateAssetsResponse(created=created)
