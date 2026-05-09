"""DashboardService — read-only system metrics for /admin/dashboard."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.assets.models import Asset, AssetCycle, CycleStatus
from app.domain.consumers.models import Consumer
from app.domain.deposits.models import DepositRecord, DepositStatus
from app.domain.orders.models import Order, OrderStatus
from app.domain.rewards.models import RewardTransaction


@dataclass(frozen=True)
class DashboardSummary:
    total_assets: int
    assets_by_status: dict[str, int]
    active_deposits: int
    released_deposits: int
    charged_deposits: int
    total_consumers: int
    total_points_granted: int
    total_orders: int
    orders_by_status: dict[str, int]
    completed_cycles: int
    active_cycles: int
    avg_wallet_balance: float


class DashboardService:
    @staticmethod
    async def summary(session: AsyncSession) -> DashboardSummary:
        # Asset counts.
        total_assets = (await session.execute(select(func.count(Asset.id)))).scalar() or 0
        by_status_rows = (
            await session.execute(select(Asset.status, func.count(Asset.id)).group_by(Asset.status))
        ).all()
        assets_by_status = {status.value: count for status, count in by_status_rows}

        # Deposit outcomes.
        active_deposits = (
            await session.execute(
                select(func.count(DepositRecord.id)).where(
                    DepositRecord.status == DepositStatus.ACTIVE
                )
            )
        ).scalar() or 0
        released_deposits = (
            await session.execute(
                select(func.count(DepositRecord.id)).where(
                    DepositRecord.status == DepositStatus.RELEASED
                )
            )
        ).scalar() or 0
        charged_deposits = (
            await session.execute(
                select(func.count(DepositRecord.id)).where(
                    DepositRecord.status == DepositStatus.CHARGED
                )
            )
        ).scalar() or 0

        total_consumers = (await session.execute(select(func.count(Consumer.id)))).scalar() or 0
        total_points_granted = (
            await session.execute(select(func.coalesce(func.sum(RewardTransaction.points), 0)))
        ).scalar() or 0
        avg_wallet = (
            await session.execute(select(func.coalesce(func.avg(Consumer.wallet_balance), 0)))
        ).scalar() or 0

        total_orders = (await session.execute(select(func.count(Order.id)))).scalar() or 0
        order_status_rows = (
            await session.execute(select(Order.status, func.count(Order.id)).group_by(Order.status))
        ).all()
        orders_by_status = {status.value: count for status, count in order_status_rows}

        completed_cycles = (
            await session.execute(
                select(func.count(AssetCycle.id)).where(AssetCycle.status == CycleStatus.COMPLETED)
            )
        ).scalar() or 0
        active_cycles = (
            await session.execute(
                select(func.count(AssetCycle.id)).where(AssetCycle.status == CycleStatus.ACTIVE)
            )
        ).scalar() or 0

        return DashboardSummary(
            total_assets=total_assets,
            assets_by_status=assets_by_status,
            active_deposits=active_deposits,
            released_deposits=released_deposits,
            charged_deposits=charged_deposits,
            total_consumers=total_consumers,
            total_points_granted=int(total_points_granted),
            total_orders=total_orders,
            orders_by_status={
                **{s.value: 0 for s in OrderStatus},
                **orders_by_status,
            },
            completed_cycles=completed_cycles,
            active_cycles=active_cycles,
            avg_wallet_balance=float(avg_wallet),
        )
