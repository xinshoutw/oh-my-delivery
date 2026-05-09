"""DispatchService: cleaning-center → restaurant batch handoff."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ids import new_uuid7
from app.domain.assets.enums import ActorRole, AssetStatus, HolderType
from app.domain.assets.models import Asset, AssetCycle, AssetEventType, CycleStatus
from app.domain.assets.state_machine import assert_transition
from app.domain.audit.service import AuditService
from app.domain.dispatches.models import Dispatch, DispatchAsset, DispatchStatus
from app.domain.hashchain.service import HashChainService


class DispatchService:
    @staticmethod
    async def prepare_assets_for_dispatch(
        session: AsyncSession,
        *,
        asset_ids: list[uuid.UUID],
        cleaning_center_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        """Move at_cleaning_center assets through washing → cleaned_ready.

        Bundles WashingStarted + WashingCompleted + AssetMarkedReady events so
        a freshly-created batch can be readied in one call.
        """
        if len(set(asset_ids)) != len(asset_ids):
            raise HTTPException(status_code=400, detail="duplicate asset_ids")

        assets = await _load_assets_for_update(session, asset_ids, cleaning_center_id)
        now = datetime.now(UTC)

        for asset in assets:
            if asset.status != AssetStatus.AT_CLEANING_CENTER:
                raise HTTPException(
                    status_code=409,
                    detail=f"asset {asset.id} not in at_cleaning_center (got {asset.status.value})",
                )
            for src, dst, event_type in (
                (
                    AssetStatus.AT_CLEANING_CENTER,
                    AssetStatus.WASHING,
                    AssetEventType.WASHING_STARTED,
                ),
                (AssetStatus.WASHING, AssetStatus.CLEANED_READY, AssetEventType.WASHING_COMPLETED),
            ):
                assert_transition(src, dst, ActorRole.CLEANING_CENTER)
                asset.status = dst
                await HashChainService.append(
                    session,
                    asset_id=asset.id,
                    event_type=event_type,
                    actor_role=ActorRole.CLEANING_CENTER,
                    actor_id=actor_id,
                    occurred_at=now,
                    lock_asset=False,
                )

            asset.last_washed_at = now

            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.ASSET_MARKED_READY,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                occurred_at=now,
                lock_asset=False,
            )

            session.add(asset)

        await AuditService.record(
            session,
            actor_type=ActorRole.CLEANING_CENTER.value,
            actor_id=actor_id,
            action="cleaning.batch_mark_ready",
            target_type="cleaning_center",
            target_id=cleaning_center_id,
            after={"asset_ids": [str(a.id) for a in assets]},
        )

        return [asset.id for asset in assets]

    @staticmethod
    async def create_dispatch(
        session: AsyncSession,
        *,
        cleaning_center_id: uuid.UUID,
        restaurant_id: uuid.UUID,
        asset_ids: list[uuid.UUID],
        note: str | None,
        actor_id: uuid.UUID,
    ) -> Dispatch:
        if len(set(asset_ids)) != len(asset_ids):
            raise HTTPException(status_code=400, detail="duplicate asset_ids")

        assets = await _load_assets_for_update(session, asset_ids, cleaning_center_id)
        now = datetime.now(UTC)

        for asset in assets:
            if asset.status != AssetStatus.CLEANED_READY:
                raise HTTPException(
                    status_code=409,
                    detail=f"asset {asset.id} not cleaned_ready (got {asset.status.value})",
                )

        dispatch = Dispatch(
            id=new_uuid7(),
            cleaning_center_id=cleaning_center_id,
            restaurant_id=restaurant_id,
            status=DispatchStatus.PENDING,
            note=note,
            created_at=now,
        )
        session.add(dispatch)

        for asset in assets:
            session.add(DispatchAsset(dispatch_id=dispatch.id, asset_id=asset.id))

            assert_transition(
                asset.status, AssetStatus.IN_TRANSIT_TO_RESTAURANT, ActorRole.CLEANING_CENTER
            )

            cycle = await _open_or_advance_cycle(session, asset)
            asset.current_cycle_id = cycle.id

            asset.status = AssetStatus.IN_TRANSIT_TO_RESTAURANT
            session.add(asset)

            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.ASSET_DISPATCHED_TO_RESTAURANT,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                cycle_id=cycle.id,
                from_holder_type=HolderType.CLEANING_CENTER,
                from_holder_id=cleaning_center_id,
                to_holder_type=HolderType.RESTAURANT,
                to_holder_id=restaurant_id,
                occurred_at=now,
                lock_asset=False,
                metadata={"dispatch_id": str(dispatch.id)},
            )

        await AuditService.record(
            session,
            actor_type=ActorRole.CLEANING_CENTER.value,
            actor_id=actor_id,
            action="dispatch.create",
            target_type="dispatch",
            target_id=dispatch.id,
            after={
                "cleaning_center_id": str(cleaning_center_id),
                "restaurant_id": str(restaurant_id),
                "asset_count": len(assets),
            },
        )

        await session.flush()
        return dispatch

    @staticmethod
    async def acknowledge_dispatch(
        session: AsyncSession,
        *,
        dispatch_id: uuid.UUID,
        restaurant_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> tuple[Dispatch, list[uuid.UUID]]:
        dispatch = (
            await session.execute(
                select(Dispatch).where(Dispatch.id == dispatch_id).with_for_update()
            )
        ).scalar_one_or_none()
        if dispatch is None:
            raise HTTPException(status_code=404, detail="dispatch not found")
        if dispatch.restaurant_id != restaurant_id:
            raise HTTPException(status_code=403, detail="dispatch belongs to another restaurant")
        if dispatch.status != DispatchStatus.PENDING:
            raise HTTPException(
                status_code=409,
                detail=f"dispatch already {dispatch.status.value}",
            )

        asset_ids = [
            row[0]
            for row in (
                await session.execute(
                    select(DispatchAsset.asset_id).where(DispatchAsset.dispatch_id == dispatch.id)
                )
            ).all()
        ]
        assets = await _load_assets_for_update_any_holder(session, asset_ids)
        now = datetime.now(UTC)

        for asset in assets:
            if asset.status != AssetStatus.IN_TRANSIT_TO_RESTAURANT:
                raise HTTPException(
                    status_code=409,
                    detail=f"asset {asset.id} not in_transit (got {asset.status.value})",
                )
            assert_transition(asset.status, AssetStatus.AT_RESTAURANT, ActorRole.RESTAURANT)
            asset.status = AssetStatus.AT_RESTAURANT
            asset.physical_holder_type = HolderType.RESTAURANT
            asset.physical_holder_id = restaurant_id
            asset.responsible_party_type = HolderType.RESTAURANT
            asset.responsible_party_id = restaurant_id
            session.add(asset)

            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.ASSET_RECEIVED_BY_RESTAURANT,
                actor_role=ActorRole.RESTAURANT,
                actor_id=actor_id,
                cycle_id=asset.current_cycle_id,
                from_holder_type=HolderType.CLEANING_CENTER,
                from_holder_id=dispatch.cleaning_center_id,
                to_holder_type=HolderType.RESTAURANT,
                to_holder_id=restaurant_id,
                occurred_at=now,
                lock_asset=False,
                metadata={"dispatch_id": str(dispatch.id)},
            )

        dispatch.status = DispatchStatus.ACKNOWLEDGED
        dispatch.acknowledged_at = now
        dispatch.acknowledged_by_actor_id = actor_id
        session.add(dispatch)

        await AuditService.record(
            session,
            actor_type=ActorRole.RESTAURANT.value,
            actor_id=actor_id,
            action="dispatch.acknowledge",
            target_type="dispatch",
            target_id=dispatch.id,
            after={"asset_count": len(assets)},
        )

        await session.flush()
        return dispatch, [asset.id for asset in assets]


async def _load_assets_for_update(
    session: AsyncSession,
    asset_ids: list[uuid.UUID],
    holder_id: uuid.UUID,
) -> list[Asset]:
    stmt = select(Asset).where(Asset.id.in_(asset_ids)).with_for_update()
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) != len(asset_ids):
        missing = set(asset_ids) - {a.id for a in rows}
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset(s) not found: {sorted(str(m) for m in missing)}",
        )
    foreign = [a.id for a in rows if a.physical_holder_id != holder_id]
    if foreign:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"asset(s) not held by this organization: {sorted(str(i) for i in foreign)}",
        )
    return list(rows)


async def _load_assets_for_update_any_holder(
    session: AsyncSession,
    asset_ids: list[uuid.UUID],
) -> list[Asset]:
    stmt = select(Asset).where(Asset.id.in_(asset_ids)).with_for_update()
    rows = (await session.execute(stmt)).scalars().all()
    if len(rows) != len(asset_ids):
        missing = set(asset_ids) - {a.id for a in rows}
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"asset(s) not found: {sorted(str(m) for m in missing)}",
        )
    return list(rows)


async def _open_or_advance_cycle(session: AsyncSession, asset: Asset) -> AssetCycle:
    """Open cycle 1 on first dispatch; later dispatches reuse the active cycle.

    Cycle close happens when the asset is marked ready again post-washing,
    not at dispatch time. So a re-dispatched asset keeps its existing cycle.
    """
    if asset.current_cycle_id is not None:
        cycle = (
            await session.execute(select(AssetCycle).where(AssetCycle.id == asset.current_cycle_id))
        ).scalar_one()
        return cycle

    last_cycle_number = (
        await session.execute(
            select(AssetCycle.cycle_number)
            .where(AssetCycle.asset_id == asset.id)
            .order_by(AssetCycle.cycle_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none() or 0

    cycle = AssetCycle(
        id=new_uuid7(),
        asset_id=asset.id,
        cycle_number=last_cycle_number + 1,
        started_at=datetime.now(UTC),
        ended_at=None,
        start_event_id=None,
        end_event_id=None,
        status=CycleStatus.ACTIVE,
    )
    session.add(cycle)
    await session.flush()
    return cycle
