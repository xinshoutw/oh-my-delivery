from __future__ import annotations

import uuid

import pytest
from app.core.config import get_settings
from app.core.hashing import hash_asset_token, hash_short_code
from app.domain.assets.enums import AssetStatus, AssetType, HolderType
from app.domain.assets.models import Asset, AssetEvent, AssetEventType
from app.domain.assets.service import AssetService
from app.domain.audit.models import AuditLog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_assets_persists_rows_and_returns_one_time_token(
    db_session: AsyncSession,
) -> None:
    cleaning_center_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    created = await AssetService.create_assets(
        db_session,
        asset_type=AssetType.MEAL_BOX,
        count=3,
        cleaning_center_id=cleaning_center_id,
        actor_id=actor_id,
    )
    await db_session.flush()

    assert len(created) == 3
    settings = get_settings()
    for item in created:
        assert item.asset_type == AssetType.MEAL_BOX
        assert item.status == AssetStatus.AT_CLEANING_CENTER
        assert item.asset_token.startswith(settings.asset_token_prefix)
        assert len(item.short_code) == settings.short_code_length

    assets = (await db_session.execute(select(Asset))).scalars().all()
    assert len(assets) == 3

    one = next(iter(created))
    db_asset = (await db_session.execute(select(Asset).where(Asset.id == one.id))).scalar_one()
    assert db_asset.short_code == one.short_code
    assert db_asset.token_hash == hash_asset_token(one.asset_token, settings.server_secret)
    assert db_asset.short_code_hash == hash_short_code(one.short_code)
    assert db_asset.physical_holder_type == HolderType.CLEANING_CENTER
    assert db_asset.physical_holder_id == cleaning_center_id
    assert db_asset.responsible_party_type == HolderType.CLEANING_CENTER


@pytest.mark.asyncio
async def test_create_assets_writes_chain_events_and_audit_logs(
    db_session: AsyncSession,
) -> None:
    cleaning_center_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    created = await AssetService.create_assets(
        db_session,
        asset_type=AssetType.DRINK_CUP,
        count=2,
        cleaning_center_id=cleaning_center_id,
        actor_id=actor_id,
    )
    await db_session.flush()

    events = (await db_session.execute(select(AssetEvent))).scalars().all()
    assert len(events) == 2
    for event in events:
        assert event.event_type == AssetEventType.ASSET_CREATED
        assert event.previous_event_hash is None  # first event in each per-asset chain
        assert event.event_hash and len(event.event_hash) == 64
        assert event.to_holder_type == HolderType.CLEANING_CENTER

    # Each created asset has its own audit log entry.
    logs = (await db_session.execute(select(AuditLog))).scalars().all()
    actions = sorted(log.action for log in logs)
    assert actions == ["asset.create", "asset.create"]
    assert {log.target_id for log in logs} == {item.id for item in created}


@pytest.mark.asyncio
async def test_create_assets_short_codes_are_unique_within_batch(
    db_session: AsyncSession,
) -> None:
    cleaning_center_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    created = await AssetService.create_assets(
        db_session,
        asset_type=AssetType.MEAL_BOX,
        count=20,
        cleaning_center_id=cleaning_center_id,
        actor_id=actor_id,
    )
    await db_session.flush()

    short_codes = {item.short_code for item in created}
    tokens = {item.asset_token for item in created}
    assert len(short_codes) == 20
    assert len(tokens) == 20
