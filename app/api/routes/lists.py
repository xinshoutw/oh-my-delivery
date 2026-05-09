"""Read-only list endpoints powering the web UI's selection screens.

Each role gets a query that surfaces work-to-do without forcing operators to
type UUIDs. All lists honor the actor headers and only return rows scoped to
the caller (couriers see their own orders, restaurants see their own dispatches,
etc.). Admin can pass override query params to widen scope.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_actor, get_db_session, require_role
from app.domain.assets.enums import ActorRole, AssetStatus, AssetType, HolderType
from app.domain.assets.models import Asset
from app.domain.deposits.models import DepositRecord, DepositStatus
from app.domain.dispatches.models import Dispatch, DispatchAsset, DispatchStatus
from app.domain.orders.models import Order, OrderStatus

router = APIRouter(prefix="/lists", tags=["lists"])


# --- Consumer holdings -------------------------------------------------------


class HoldingItem(BaseModel):
    asset_id: uuid.UUID
    asset_type: AssetType
    short_code: str
    status: AssetStatus
    deposit_id: uuid.UUID | None
    deposit_amount: int | None
    deposit_status: DepositStatus | None
    borrowed_at: datetime | None
    due_at: datetime | None
    reward_cutoff_at: datetime | None


@router.get("/consumer/holdings", response_model=list[HoldingItem])
async def consumer_holdings(
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CONSUMER, ActorRole.ADMIN)),
    consumer_id: uuid.UUID | None = Query(default=None),
) -> Sequence[HoldingItem]:
    target = consumer_id if (actor.role == ActorRole.ADMIN and consumer_id) else actor.id
    stmt = (
        select(Asset, DepositRecord)
        .outerjoin(
            DepositRecord,
            (DepositRecord.asset_id == Asset.id)
            & (
                DepositRecord.status.in_(
                    [DepositStatus.ACTIVE, DepositStatus.PENDING_RETURN_CONFIRMATION]
                )
            ),
        )
        .where(
            Asset.physical_holder_type == HolderType.CONSUMER,
            Asset.physical_holder_id == target,
        )
        .order_by(Asset.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()
    items: list[HoldingItem] = []
    for asset, deposit in rows:
        items.append(
            HoldingItem(
                asset_id=asset.id,
                asset_type=asset.asset_type,
                short_code=asset.short_code,
                status=asset.status,
                deposit_id=deposit.id if deposit else None,
                deposit_amount=deposit.amount if deposit else None,
                deposit_status=deposit.status if deposit else None,
                borrowed_at=deposit.borrowed_at if deposit else None,
                due_at=deposit.due_at if deposit else None,
                reward_cutoff_at=deposit.reward_cutoff_at if deposit else None,
            )
        )
    return items


# --- Courier orders ----------------------------------------------------------


class CourierOrderItem(BaseModel):
    order_id: uuid.UUID
    external_order_id: str
    status: OrderStatus
    restaurant_id: uuid.UUID
    consumer_id: uuid.UUID
    expected_asset_manifest: dict[str, int]
    created_at: datetime


@router.get("/courier/orders", response_model=list[CourierOrderItem])
async def courier_orders(
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.COURIER, ActorRole.ADMIN)),
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    courier_id: uuid.UUID | None = Query(default=None),
) -> Sequence[CourierOrderItem]:
    target = courier_id if (actor.role == ActorRole.ADMIN and courier_id) else actor.id
    stmt = select(Order).where(Order.courier_id == target).order_by(Order.created_at.desc())
    if status_filter is not None:
        stmt = stmt.where(Order.status == status_filter)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        CourierOrderItem(
            order_id=o.id,
            external_order_id=o.external_order_id,
            status=o.status,
            restaurant_id=o.restaurant_id,
            consumer_id=o.consumer_id,
            expected_asset_manifest=o.expected_asset_manifest,
            created_at=o.created_at,
        )
        for o in rows
    ]


# --- Restaurant dispatches ---------------------------------------------------


class RestaurantDispatchItem(BaseModel):
    dispatch_id: uuid.UUID
    cleaning_center_id: uuid.UUID
    status: DispatchStatus
    asset_count: int
    note: str | None
    created_at: datetime
    acknowledged_at: datetime | None


@router.get("/restaurant/dispatches", response_model=list[RestaurantDispatchItem])
async def restaurant_dispatches(
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.RESTAURANT, ActorRole.ADMIN)),
    status_filter: DispatchStatus | None = Query(default=None, alias="status"),
    restaurant_id: uuid.UUID | None = Query(default=None),
) -> Sequence[RestaurantDispatchItem]:
    if actor.role == ActorRole.RESTAURANT:
        if actor.organization_id is None:
            raise HTTPException(status_code=400, detail="X-Organization-Id required")
        target = actor.organization_id
    else:
        if restaurant_id is None:
            raise HTTPException(status_code=400, detail="restaurant_id required for admin scope")
        target = restaurant_id

    asset_count_subq = (
        select(DispatchAsset.dispatch_id, func.count(DispatchAsset.asset_id).label("ct"))
        .group_by(DispatchAsset.dispatch_id)
        .subquery()
    )
    stmt = (
        select(Dispatch, asset_count_subq.c.ct)
        .outerjoin(asset_count_subq, asset_count_subq.c.dispatch_id == Dispatch.id)
        .where(Dispatch.restaurant_id == target)
        .order_by(Dispatch.created_at.desc())
    )
    if status_filter is not None:
        stmt = stmt.where(Dispatch.status == status_filter)
    rows = (await session.execute(stmt)).all()
    return [
        RestaurantDispatchItem(
            dispatch_id=d.id,
            cleaning_center_id=d.cleaning_center_id,
            status=d.status,
            asset_count=int(ct or 0),
            note=d.note,
            created_at=d.created_at,
            acknowledged_at=d.acknowledged_at,
        )
        for d, ct in rows
    ]


# --- Restaurant inventory ----------------------------------------------------


class RestaurantInventoryItem(BaseModel):
    asset_id: uuid.UUID
    asset_type: AssetType
    short_code: str
    status: AssetStatus
    usage_count: int


@router.get("/restaurant/inventory", response_model=list[RestaurantInventoryItem])
async def restaurant_inventory(
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(
        require_role(
            ActorRole.RESTAURANT,
            ActorRole.COURIER,
            ActorRole.ADMIN,
        )
    ),
    restaurant_id: uuid.UUID | None = Query(default=None),
    order_id: uuid.UUID | None = Query(default=None),
    asset_type: AssetType | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> Sequence[RestaurantInventoryItem]:
    """List assets currently at a restaurant.

    Resolution rules:
    - RESTAURANT actor: scoped to own organization (X-Organization-Id required).
    - COURIER actor: must pass order_id; the order's restaurant_id is used,
      and the courier must own the order.
    - ADMIN actor: must pass restaurant_id (or order_id, which resolves to one).
    """
    target: uuid.UUID
    if actor.role == ActorRole.RESTAURANT:
        if actor.organization_id is None:
            raise HTTPException(status_code=400, detail="X-Organization-Id required")
        target = actor.organization_id
    elif actor.role == ActorRole.COURIER:
        if order_id is None:
            raise HTTPException(status_code=400, detail="order_id required for courier")
        order = (
            await session.execute(select(Order).where(Order.id == order_id))
        ).scalar_one_or_none()
        if order is None:
            raise HTTPException(status_code=404, detail="order not found")
        if order.courier_id != actor.id:
            raise HTTPException(status_code=403, detail="order not owned by courier")
        target = order.restaurant_id
    else:  # ADMIN
        if order_id is not None:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalar_one_or_none()
            if order is None:
                raise HTTPException(status_code=404, detail="order not found")
            target = order.restaurant_id
        elif restaurant_id is not None:
            target = restaurant_id
        else:
            raise HTTPException(
                status_code=400,
                detail="restaurant_id or order_id required for admin scope",
            )

    stmt = (
        select(Asset)
        .where(
            Asset.physical_holder_type == HolderType.RESTAURANT,
            Asset.physical_holder_id == target,
            Asset.status == AssetStatus.AT_RESTAURANT,
        )
        .order_by(Asset.created_at.desc())
        .limit(limit)
    )
    if asset_type is not None:
        stmt = stmt.where(Asset.asset_type == asset_type)
    rows = (await session.execute(stmt)).scalars().all()
    return [
        RestaurantInventoryItem(
            asset_id=a.id,
            asset_type=a.asset_type,
            short_code=a.short_code,
            status=a.status,
            usage_count=a.usage_count,
        )
        for a in rows
    ]


# --- Cleaning center assets --------------------------------------------------


class CleaningAssetItem(BaseModel):
    asset_id: uuid.UUID
    asset_type: AssetType
    short_code: str
    status: AssetStatus
    physical_holder_type: HolderType | None
    usage_count: int
    last_washed_at: datetime | None


@router.get("/cleaning/assets", response_model=list[CleaningAssetItem])
async def cleaning_assets(
    session: AsyncSession = Depends(get_db_session),
    actor: Actor = Depends(require_role(ActorRole.CLEANING_CENTER, ActorRole.ADMIN)),
    status_filter: AssetStatus | None = Query(default=None, alias="status"),
    asset_type: AssetType | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> Sequence[CleaningAssetItem]:
    org_id: uuid.UUID | None = (
        actor.organization_id if actor.role == ActorRole.CLEANING_CENTER else None
    )
    stmt = select(Asset).order_by(Asset.created_at.desc()).limit(limit)
    if status_filter is not None:
        stmt = stmt.where(Asset.status == status_filter)
    if asset_type is not None:
        stmt = stmt.where(Asset.asset_type == asset_type)
    if org_id is not None:
        stmt = stmt.where(
            (
                (Asset.physical_holder_type == HolderType.CLEANING_CENTER)
                & (Asset.physical_holder_id == org_id)
            )
            | (Asset.physical_holder_type.is_(None))
        )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        CleaningAssetItem(
            asset_id=a.id,
            asset_type=a.asset_type,
            short_code=a.short_code,
            status=a.status,
            physical_holder_type=a.physical_holder_type,
            usage_count=a.usage_count,
            last_washed_at=a.last_washed_at,
        )
        for a in rows
    ]


# --- Public-ish helpers used by the web UI without role lock-in -------------


class AssetLookupItem(BaseModel):
    asset_id: uuid.UUID
    asset_type: AssetType
    short_code: str
    status: AssetStatus


@router.get("/lookup/asset", response_model=AssetLookupItem)
async def lookup_asset(
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(get_actor),
    short_code: str | None = Query(default=None, max_length=16),
) -> AssetLookupItem:
    """Resolve a public short_code to an asset for any authenticated actor.

    Useful for confirming a manually typed code before submitting a scan.
    """
    if not short_code:
        raise HTTPException(status_code=400, detail="short_code required")
    code = short_code.strip().upper()
    asset = (
        await session.execute(select(Asset).where(Asset.short_code == code))
    ).scalar_one_or_none()
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return AssetLookupItem(
        asset_id=asset.id,
        asset_type=asset.asset_type,
        short_code=asset.short_code,
        status=asset.status,
    )
