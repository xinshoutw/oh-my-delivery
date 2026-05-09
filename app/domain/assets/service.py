"""AssetService: cleaning-center asset creation and lifecycle helpers.

State transitions go through :mod:`app.domain.assets.state_machine` so the
audit / hash-chain trail stays consistent with the legal transition map.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.hashing import hash_asset_token, hash_short_code
from app.core.ids import new_asset_token, new_short_code, new_uuid7
from app.domain.assets.enums import (
    ActorRole,
    AssetStatus,
    AssetType,
    HolderType,
)
from app.domain.assets.models import Asset, AssetEventType
from app.domain.assets.schemas import AssetCreatedItem
from app.domain.assets.state_machine import assert_transition
from app.domain.audit.service import AuditService
from app.domain.hashchain.service import HashChainService

_MAX_SHORTCODE_RETRY = 8


class AssetService:
    @staticmethod
    async def create_assets(
        session: AsyncSession,
        *,
        asset_type: AssetType,
        count: int,
        cleaning_center_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> list[AssetCreatedItem]:
        settings = get_settings()
        created: list[AssetCreatedItem] = []
        now = datetime.now(UTC)

        for _ in range(count):
            token, short_code, asset = await _persist_new_asset(
                session=session,
                settings_token_prefix=settings.asset_token_prefix,
                token_random_len=settings.asset_token_random_chars,
                short_code_len=settings.short_code_length,
                asset_type=asset_type,
                cleaning_center_id=cleaning_center_id,
                created_at=now,
            )
            await HashChainService.append(
                session,
                asset_id=asset.id,
                event_type=AssetEventType.ASSET_CREATED,
                actor_role=ActorRole.CLEANING_CENTER,
                actor_id=actor_id,
                to_holder_type=HolderType.CLEANING_CENTER,
                to_holder_id=cleaning_center_id,
                metadata={"asset_type": asset_type.value},
                occurred_at=now,
                lock_asset=False,
            )
            await AuditService.record(
                session,
                actor_type=ActorRole.CLEANING_CENTER.value,
                actor_id=actor_id,
                action="asset.create",
                target_type="asset",
                target_id=asset.id,
                after={
                    "asset_type": asset_type.value,
                    "short_code": short_code,
                    "status": asset.status.value,
                },
            )
            created.append(
                AssetCreatedItem(
                    id=asset.id,
                    asset_type=asset.asset_type,
                    short_code=short_code,
                    asset_token=token,
                    status=asset.status,
                )
            )

        return created

    @staticmethod
    async def transition(
        session: AsyncSession,
        asset: Asset,
        *,
        target: AssetStatus,
        actor_role: ActorRole,
    ) -> None:
        assert_transition(asset.status, target, actor_role)
        asset.status = target
        session.add(asset)


async def _persist_new_asset(
    *,
    session: AsyncSession,
    settings_token_prefix: str,
    token_random_len: int,
    short_code_len: int,
    asset_type: AssetType,
    cleaning_center_id: uuid.UUID,
    created_at: datetime,
) -> tuple[str, str, Asset]:
    settings = get_settings()
    last_error: Exception | None = None
    for _ in range(_MAX_SHORTCODE_RETRY):
        token = new_asset_token(prefix=settings_token_prefix, random_length=token_random_len)
        short_code = new_short_code(short_code_len)
        asset = Asset(
            id=new_uuid7(),
            asset_type=asset_type,
            short_code=short_code,
            short_code_hash=hash_short_code(short_code),
            token_hash=hash_asset_token(token, settings.server_secret),
            status=AssetStatus.AT_CLEANING_CENTER,
            physical_holder_type=HolderType.CLEANING_CENTER,
            physical_holder_id=cleaning_center_id,
            responsible_party_type=HolderType.CLEANING_CENTER,
            responsible_party_id=cleaning_center_id,
            current_cycle_id=None,
            usage_count=0,
            last_washed_at=None,
            created_at=created_at,
            retired_at=None,
        )
        session.add(asset)
        try:
            await session.flush()
        except IntegrityError as err:
            last_error = err
            await session.rollback()
            continue
        return token, short_code, asset

    raise RuntimeError("Failed to allocate unique short_code / token after retries") from last_error
