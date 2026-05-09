"""CleaningService — final confirmation, deposit settlement, reward, cycle close.

This is the D12 closing service: only `cleaning_confirmed_at` (recorded here)
controls deposit release / charge and reward eligibility. The consumer's
scan + the sensor event are corroborating evidence; this service is the
sole source of truth.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.hashing import hash_asset_token, hash_short_code
from app.core.ids import new_uuid7
from app.domain.assets.enums import (
    ActorRole,
    AssetStatus,
    HolderType,
)
from app.domain.assets.models import Asset, AssetCycle, AssetEventType, CycleStatus
from app.domain.assets.state_machine import assert_transition
from app.domain.audit.service import AuditService
from app.domain.consumers.models import Consumer
from app.domain.deposits.models import DepositRecord, DepositStatus
from app.domain.hashchain.service import HashChainService
from app.domain.returns.models import ReturnSession, ReturnSessionStatus
from app.domain.rewards.models import (
    REWARD_REASON_RETURN,
    RewardStatus,
    RewardTransaction,
)
from app.domain.washing.models import (
    WashingBatch,
    WashingBatchItem,
    WashingBatchStatus,
)


@dataclass(frozen=True)
class ReceivedAssetReport:
    asset_id: uuid.UUID
    asset_type: str
    deposit_outcome: str  # released / charged / no_deposit
    reward_granted: bool
    reward_points: int


_RECEIVABLE_STATES = frozenset(
    {
        AssetStatus.DEPOSITED_IN_RETURN_BOX,
        AssetStatus.COLLECTED_BY_RECYCLING_UNIT,
        AssetStatus.LOST,
    }
)


class CleaningService:
    @staticmethod
    async def receive_assets(
        session: AsyncSession,
        *,
        asset_tokens: list[str],
        cleaning_center_id: uuid.UUID,
        actor_id: uuid.UUID,
        short_codes: list[str] | None = None,
    ) -> list[ReceivedAssetReport]:
        short_codes = short_codes or []
        if not asset_tokens and not short_codes:
            raise HTTPException(
                status_code=400,
                detail="asset_tokens or short_codes required",
            )
        settings = get_settings()
        now = datetime.now(UTC)

        assets = await _resolve_assets(session, asset_tokens, short_codes, settings)
        reports: list[ReceivedAssetReport] = []

        for asset in assets:
            if asset.status not in _RECEIVABLE_STATES:
                raise HTTPException(
                    status_code=409,
                    detail=(f"asset {asset.id} not receivable from {asset.status.value}"),
                )

            assert_transition(
                asset.status, AssetStatus.RETURNED_TO_CLEANING_CENTER, ActorRole.CLEANING_CENTER
            )
            asset.status = AssetStatus.RETURNED_TO_CLEANING_CENTER
            asset.physical_holder_type = HolderType.CLEANING_CENTER
            asset.physical_holder_id = cleaning_center_id
            asset.responsible_party_type = HolderType.CLEANING_CENTER
            asset.responsible_party_id = cleaning_center_id
            session.add(asset)

            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.CLEANING_CENTER_RECEIVED,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                cycle_id=asset.current_cycle_id,
                to_holder_type=HolderType.CLEANING_CENTER,
                to_holder_id=cleaning_center_id,
                occurred_at=now,
                lock_asset=False,
            )

            await _close_return_sessions(session, asset_id=asset.id, cleaning_confirmed_at=now)
            deposit_outcome, reward_granted = await _settle_deposit_and_reward(
                session,
                asset=asset,
                cleaning_confirmed_at=now,
                settings=settings,
            )

            assert_transition(asset.status, AssetStatus.UNDER_INSPECTION, ActorRole.CLEANING_CENTER)
            asset.status = AssetStatus.UNDER_INSPECTION
            session.add(asset)

            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.CLEANING_INSPECTION_STARTED,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                cycle_id=asset.current_cycle_id,
                occurred_at=now,
                lock_asset=False,
            )

            reports.append(
                ReceivedAssetReport(
                    asset_id=asset.id,
                    asset_type=asset.asset_type.value,
                    deposit_outcome=deposit_outcome,
                    reward_granted=reward_granted,
                    reward_points=settings.reward_points_per_return if reward_granted else 0,
                )
            )

        await AuditService.record(
            session,
            actor_type=ActorRole.CLEANING_CENTER.value,
            actor_id=actor_id,
            action="cleaning.receive",
            target_type="cleaning_center",
            target_id=cleaning_center_id,
            after={"asset_count": len(reports)},
        )
        await session.flush()
        return reports

    @staticmethod
    async def inspect(
        session: AsyncSession,
        *,
        asset_id: uuid.UUID,
        condition: str,
        component_status: dict[str, str] | None,
        notes: str | None,
        cleaning_center_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> Asset:
        if condition not in {"usable", "damaged", "retired"}:
            raise HTTPException(status_code=400, detail="condition must be usable/damaged/retired")

        asset = (
            await session.execute(select(Asset).where(Asset.id == asset_id).with_for_update())
        ).scalar_one_or_none()
        if asset is None:
            raise HTTPException(status_code=404, detail="asset not found")
        if asset.status != AssetStatus.UNDER_INSPECTION:
            raise HTTPException(
                status_code=409,
                detail=f"asset is {asset.status.value}; cannot inspect",
            )

        now = datetime.now(UTC)
        target = {
            "usable": AssetStatus.WASHING,
            "damaged": AssetStatus.DAMAGED,
            "retired": AssetStatus.RETIRED,
        }[condition]
        assert_transition(asset.status, target, ActorRole.CLEANING_CENTER)
        asset.status = target
        if target == AssetStatus.RETIRED:
            asset.retired_at = now
        session.add(asset)

        batch = await _ensure_active_batch(
            session, cleaning_center_id=cleaning_center_id, operator_id=actor_id, now=now
        )
        item = WashingBatchItem(
            id=new_uuid7(),
            batch_id=batch.id,
            asset_id=asset.id,
            pre_check_status=condition,
            post_check_status=None,
            component_status=component_status,
            notes=notes,
            created_at=now,
        )
        session.add(item)

        await HashChainService.append(
            session,
            asset_id=asset.id,
            event_type=AssetEventType.CLEANING_INSPECTION_COMPLETED,
            actor_role=ActorRole.CLEANING_CENTER,
            actor_id=actor_id,
            cycle_id=asset.current_cycle_id,
            occurred_at=now,
            lock_asset=False,
            metadata={
                "condition": condition,
                "components": sorted((component_status or {}).keys()),
            },
        )
        if target == AssetStatus.WASHING:
            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.WASHING_STARTED,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                cycle_id=asset.current_cycle_id,
                occurred_at=now,
                lock_asset=False,
            )
        elif target == AssetStatus.DAMAGED:
            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.ASSET_MARKED_DAMAGED,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                cycle_id=asset.current_cycle_id,
                occurred_at=now,
                lock_asset=False,
            )
        else:  # RETIRED
            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.ASSET_RETIRED,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                cycle_id=asset.current_cycle_id,
                occurred_at=now,
                lock_asset=False,
            )
        await session.flush()
        return asset

    @staticmethod
    async def complete_washing(
        session: AsyncSession,
        *,
        asset_ids: list[uuid.UUID],
        cleaning_center_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> list[Asset]:
        if not asset_ids:
            raise HTTPException(status_code=400, detail="asset_ids required")

        assets = list(
            (await session.execute(select(Asset).where(Asset.id.in_(asset_ids)).with_for_update()))
            .scalars()
            .all()
        )
        if len(assets) != len(set(asset_ids)):
            raise HTTPException(status_code=404, detail="some assets missing")

        now = datetime.now(UTC)
        for asset in assets:
            if asset.status != AssetStatus.WASHING:
                raise HTTPException(
                    status_code=409,
                    detail=f"asset {asset.id} not washing ({asset.status.value})",
                )
            assert_transition(asset.status, AssetStatus.CLEANED_READY, ActorRole.CLEANING_CENTER)
            asset.status = AssetStatus.CLEANED_READY
            asset.last_washed_at = now

            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.WASHING_COMPLETED,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                cycle_id=asset.current_cycle_id,
                occurred_at=now,
                lock_asset=False,
            )
            ready_event = await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.ASSET_MARKED_READY,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                cycle_id=asset.current_cycle_id,
                occurred_at=now,
                lock_asset=False,
            )

            if asset.current_cycle_id is not None:
                cycle = (
                    await session.execute(
                        select(AssetCycle)
                        .where(AssetCycle.id == asset.current_cycle_id)
                        .with_for_update()
                    )
                ).scalar_one()
                cycle.ended_at = now
                cycle.status = CycleStatus.COMPLETED
                cycle.end_event_id = ready_event.id
                session.add(cycle)
                asset.usage_count += 1
                asset.current_cycle_id = None
            session.add(asset)

        await AuditService.record(
            session,
            actor_type=ActorRole.CLEANING_CENTER.value,
            actor_id=actor_id,
            action="cleaning.complete_washing",
            target_type="cleaning_center",
            target_id=cleaning_center_id,
            after={"asset_count": len(assets)},
        )
        await session.flush()
        return list(assets)


async def _resolve_assets(
    session: AsyncSession,
    tokens: list[str],
    short_codes: list[str],
    settings: Settings,
) -> list[Asset]:
    """Resolve assets by token hash, short_code hash, or both.

    Each input is its own filter — duplicates across the two lists collapse to
    one row. We require every input to map to a row so the caller learns about
    typos instead of silently receiving fewer assets than expected.
    """
    token_hashes = {hash_asset_token(t, settings.server_secret) for t in tokens}
    code_hashes = {hash_short_code(c.strip().upper()) for c in short_codes if c.strip()}

    conditions = []
    if token_hashes:
        conditions.append(Asset.token_hash.in_(token_hashes))
    if code_hashes:
        conditions.append(Asset.short_code_hash.in_(code_hashes))
    if not conditions:
        return []
    from sqlalchemy import or_

    stmt = select(Asset).where(or_(*conditions)).with_for_update()
    rows = list((await session.execute(stmt)).scalars().all())

    found_token_hashes = {a.token_hash for a in rows}
    found_code_hashes = {a.short_code_hash for a in rows}
    missing_tokens = token_hashes - found_token_hashes
    missing_codes = code_hashes - found_code_hashes
    if missing_tokens or missing_codes:
        raise HTTPException(status_code=404, detail="some asset_tokens or short_codes not found")
    return rows


async def _close_return_sessions(
    session: AsyncSession,
    *,
    asset_id: uuid.UUID,
    cleaning_confirmed_at: datetime,
) -> None:
    rows = (
        (
            await session.execute(
                select(ReturnSession).where(
                    ReturnSession.asset_id == asset_id,
                    ReturnSession.status.in_(
                        [
                            ReturnSessionStatus.SCANNED,
                            ReturnSessionStatus.DEPOSIT_DETECTED,
                        ]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    for rs in rows:
        rs.status = ReturnSessionStatus.CONFIRMED_BY_CLEANING_CENTER
        rs.cleaning_confirmed_at = cleaning_confirmed_at
        session.add(rs)


async def _settle_deposit_and_reward(
    session: AsyncSession,
    *,
    asset: Asset,
    cleaning_confirmed_at: datetime,
    settings: Settings,
) -> tuple[str, bool]:
    if asset.current_cycle_id is None:
        return "no_deposit", False

    deposit = (
        await session.execute(
            select(DepositRecord)
            .where(
                DepositRecord.asset_id == asset.id,
                DepositRecord.cycle_id == asset.current_cycle_id,
                DepositRecord.status == DepositStatus.ACTIVE,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if deposit is None:
        return "no_deposit", False

    consumer = (
        await session.execute(
            select(Consumer).where(Consumer.id == deposit.consumer_id).with_for_update()
        )
    ).scalar_one()

    deposit.cleaning_confirmed_at = cleaning_confirmed_at
    deposit.returned_at = cleaning_confirmed_at

    if cleaning_confirmed_at <= deposit.due_at:
        deposit.status = DepositStatus.RELEASED
        deposit.released_at = cleaning_confirmed_at
        consumer.wallet_balance += deposit.amount
        outcome = "released"
    else:
        deposit.status = DepositStatus.CHARGED
        deposit.charged_at = cleaning_confirmed_at
        consumer.overdue_count += 1
        consumer.last_overdue_at = cleaning_confirmed_at
        if consumer.deposit_level < settings.deposit_max_level:
            consumer.deposit_level += 1
        consumer.current_required_deposit = (
            settings.deposit_base_amount + consumer.deposit_level * settings.deposit_step_amount
        )
        outcome = "charged"

    session.add(deposit)
    session.add(consumer)

    reward_granted = False
    elapsed = cleaning_confirmed_at - deposit.borrowed_at
    if elapsed <= timedelta(days=settings.reward_window_days):
        reward = RewardTransaction(
            id=new_uuid7(),
            consumer_id=consumer.id,
            asset_id=asset.id,
            cycle_id=asset.current_cycle_id,
            event_id=None,
            points=settings.reward_points_per_return,
            reason=REWARD_REASON_RETURN,
            status=RewardStatus.CONFIRMED,
            created_at=cleaning_confirmed_at,
        )
        session.add(reward)
        try:
            await session.flush()
            consumer.points += reward.points
            session.add(consumer)
            reward_granted = True
            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.REWARD_GRANTED,
                actor_role=ActorRole.SYSTEM,
                actor_id=consumer.id,
                cycle_id=asset.current_cycle_id,
                occurred_at=cleaning_confirmed_at,
                lock_asset=False,
                metadata={"points": reward.points, "reason": reward.reason},
            )
        except IntegrityError:
            await session.rollback()  # already exists; that's the unique guarantee at work

    await HashChainService.append(
        session,
        asset_id=asset.id,
        event_type=(
            AssetEventType.DEPOSIT_RELEASED
            if outcome == "released"
            else AssetEventType.DEPOSIT_CHARGED
        ),
        actor_role=ActorRole.SYSTEM,
        actor_id=consumer.id,
        cycle_id=asset.current_cycle_id,
        occurred_at=cleaning_confirmed_at,
        lock_asset=False,
        metadata={"amount": deposit.amount},
    )
    return outcome, reward_granted


async def _ensure_active_batch(
    session: AsyncSession,
    *,
    cleaning_center_id: uuid.UUID,
    operator_id: uuid.UUID,
    now: datetime,
) -> WashingBatch:
    existing = (
        await session.execute(
            select(WashingBatch).where(
                WashingBatch.cleaning_center_id == cleaning_center_id,
                WashingBatch.status == WashingBatchStatus.WASHING,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    batch = WashingBatch(
        id=new_uuid7(),
        cleaning_center_id=cleaning_center_id,
        operator_id=operator_id,
        status=WashingBatchStatus.WASHING,
        started_at=now,
        finished_at=None,
        created_at=now,
    )
    session.add(batch)
    await session.flush()
    return batch
