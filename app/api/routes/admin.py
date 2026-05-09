"""Admin routes: dashboard, manual scheduler triggers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_db_session, require_role
from app.domain.assets.enums import ActorRole
from app.domain.dashboard.service import DashboardService
from app.domain.hashchain.anchor_service import HashChainAnchorService
from app.domain.notifications.service import NotificationService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/dashboard")
async def get_dashboard(
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> dict:
    summary = await DashboardService.summary(session)
    return {
        "total_assets": summary.total_assets,
        "assets_by_status": summary.assets_by_status,
        "active_deposits": summary.active_deposits,
        "released_deposits": summary.released_deposits,
        "charged_deposits": summary.charged_deposits,
        "total_consumers": summary.total_consumers,
        "total_points_granted": summary.total_points_granted,
        "total_orders": summary.total_orders,
        "orders_by_status": summary.orders_by_status,
        "completed_cycles": summary.completed_cycles,
        "active_cycles": summary.active_cycles,
        "avg_wallet_balance": summary.avg_wallet_balance,
    }


@router.post("/notifications/dispatch")
async def dispatch_notifications(
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
    limit: int = Query(default=200, ge=1, le=10000),
) -> dict:
    sent = await NotificationService.dispatch_due(session, limit=limit)
    return {"dispatched": sent}


@router.post("/chain-anchors/compute")
async def compute_chain_anchor(
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
    anchor_for_yesterday: bool = Query(default=True),
) -> dict:
    target_date = (datetime.now(UTC) - timedelta(days=1 if anchor_for_yesterday else 0)).date()
    anchor = await HashChainAnchorService.compute_for_date(session, target_date)
    return {
        "anchor_date": anchor.anchor_date.isoformat(),
        "root_hash": anchor.root_hash,
        "event_count": anchor.event_count,
    }
