"""Courier routes: pickup scan session lifecycle."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_db_session, require_role
from app.domain.assets.enums import ActorRole, AssetType
from app.domain.pickup.schemas import (
    CancelPickupResponse,
    ConfirmedAssetItem,
    ConfirmPickupResponse,
    CreatePickupSessionResponse,
    ProgressEntry,
    ScanRequest,
    ScanResponse,
)
from app.domain.pickup.service import PickupSessionService

router = APIRouter(prefix="/courier", tags=["courier"])


def _progress_payload(progress: dict[AssetType, tuple[int, int]]) -> dict[AssetType, ProgressEntry]:
    return {
        asset_type: ProgressEntry(expected=expected, scanned=scanned)
        for asset_type, (expected, scanned) in progress.items()
    }


def _is_fully_scanned(progress: dict[AssetType, tuple[int, int]]) -> bool:
    return all(scanned >= expected for expected, scanned in progress.values())


@router.post(
    "/orders/{order_id}/pickup-sessions",
    response_model=CreatePickupSessionResponse,
    status_code=201,
)
async def create_pickup_session(
    order_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.COURIER, ActorRole.ADMIN)),
) -> CreatePickupSessionResponse:
    pickup = await PickupSessionService.create(
        session,
        order_id=order_id,
        courier_id=actor.id,
    )
    expires_in = max(0, int((pickup.expires_at - pickup.created_at).total_seconds()))
    expected = {AssetType(k): v for k, v in pickup.expected_manifest.items()}
    return CreatePickupSessionResponse(
        pickup_session_id=pickup.id,
        order_id=pickup.order_id,
        expected_manifest=expected,
        expires_in_seconds=expires_in,
        expires_at=pickup.expires_at,
        status=pickup.status,
    )


@router.post("/pickup-sessions/{session_id}/scan", response_model=ScanResponse)
async def scan(
    session_id: uuid.UUID,
    body: ScanRequest,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.COURIER, ActorRole.ADMIN)),
) -> ScanResponse:
    if not body.asset_token and not body.short_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="asset_token or short_code required",
        )
    _, item, progress = await PickupSessionService.scan(
        session,
        session_id=session_id,
        courier_id=actor.id,
        asset_token=body.asset_token,
        short_code=body.short_code,
    )
    asset_type_value: AssetType | None = None
    if item.asset_type:
        try:
            asset_type_value = AssetType(item.asset_type)
        except ValueError:
            asset_type_value = None
    return ScanResponse(
        accepted=item.accepted,
        already_scanned=(item.reject_reason == "already_scanned"),
        asset_id=item.asset_id,
        asset_type=asset_type_value,
        asset_public_code=None,
        reject_reason=item.reject_reason,
        progress=_progress_payload(progress),
        fully_scanned=_is_fully_scanned(progress),
    )


@router.post(
    "/pickup-sessions/{session_id}/confirm",
    response_model=ConfirmPickupResponse,
)
async def confirm_pickup(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.COURIER, ActorRole.ADMIN)),
) -> ConfirmPickupResponse:
    pickup, assets = await PickupSessionService.confirm(
        session,
        session_id=session_id,
        courier_id=actor.id,
    )
    return ConfirmPickupResponse(
        pickup_session_id=pickup.id,
        order_id=pickup.order_id,
        transferred_assets=[
            ConfirmedAssetItem(
                asset_id=a.id,
                asset_type=a.asset_type,
                public_code=a.short_code,
            )
            for a in assets
        ],
        order_status="picked_up",
    )


@router.post(
    "/pickup-sessions/{session_id}/cancel",
    response_model=CancelPickupResponse,
)
async def cancel_pickup(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.COURIER, ActorRole.ADMIN)),
) -> CancelPickupResponse:
    pickup = await PickupSessionService.cancel(
        session,
        session_id=session_id,
        courier_id=actor.id,
    )
    return CancelPickupResponse(pickup_session_id=pickup.id, status=pickup.status)
