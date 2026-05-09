"""Cleaning-center routes: asset creation, dispatch, receive, inspection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_db_session, require_role
from app.domain.assets.enums import ActorRole
from app.domain.assets.schemas import CreateAssetsRequest, CreateAssetsResponse
from app.domain.assets.service import AssetService
from app.domain.cleaning.schemas import (
    CompleteWashingRequest,
    CompleteWashingResponse,
    InspectRequest,
    InspectResponse,
    ReceiveAssetsRequest,
    ReceiveAssetsResponse,
    ReceivedAssetItem,
)
from app.domain.cleaning.service import CleaningService
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


@router.post("/receive", response_model=ReceiveAssetsResponse)
async def receive_assets(
    body: ReceiveAssetsRequest,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CLEANING_CENTER, ActorRole.ADMIN)),
) -> ReceiveAssetsResponse:
    _require_org(actor)
    assert actor.organization_id is not None
    reports = await CleaningService.receive_assets(
        session,
        asset_tokens=body.asset_tokens,
        cleaning_center_id=actor.organization_id,
        actor_id=actor.id,
    )
    return ReceiveAssetsResponse(
        received=[
            ReceivedAssetItem(
                asset_id=r.asset_id,
                asset_type=r.asset_type,
                deposit_outcome=r.deposit_outcome,
                reward_granted=r.reward_granted,
                reward_points=r.reward_points,
            )
            for r in reports
        ]
    )


@router.post("/inspection", response_model=InspectResponse)
async def inspect_asset(
    body: InspectRequest,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CLEANING_CENTER, ActorRole.ADMIN)),
) -> InspectResponse:
    _require_org(actor)
    assert actor.organization_id is not None
    asset = await CleaningService.inspect(
        session,
        asset_id=body.asset_id,
        condition=body.condition,
        component_status=body.component_status,
        notes=body.notes,
        cleaning_center_id=actor.organization_id,
        actor_id=actor.id,
    )
    return InspectResponse(asset_id=asset.id, new_status=asset.status.value)


@router.post("/washing-batches/complete", response_model=CompleteWashingResponse)
async def complete_washing_batch(
    body: CompleteWashingRequest,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CLEANING_CENTER, ActorRole.ADMIN)),
) -> CompleteWashingResponse:
    _require_org(actor)
    assert actor.organization_id is not None
    assets = await CleaningService.complete_washing(
        session,
        asset_ids=body.asset_ids,
        cleaning_center_id=actor.organization_id,
        actor_id=actor.id,
    )
    return CompleteWashingResponse(asset_ids=[a.id for a in assets])


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
