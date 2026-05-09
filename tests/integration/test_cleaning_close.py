"""Cleaning center final confirmation: deposit settle, reward, cycle close."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.domain.assets.models import Asset, AssetCycle, AssetEvent, AssetEventType, CycleStatus
from app.domain.consumers.models import Consumer
from app.domain.deposits.models import DepositRecord, DepositStatus
from app.domain.devices.service import ReturnBoxService
from app.domain.partners.service import PartnerService
from app.domain.returns.models import ReturnSession, ReturnSessionStatus
from app.domain.rewards.models import RewardTransaction
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PARTNER_KEY = "cleaning-close-key"
DEVICE_KEY = "cleaning-close-device"
SERVER_SECRET = "x" * 32


async def _seed_partner_and_box(
    sm: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    async with sm() as s:
        p = await PartnerService.create(
            s, name="P", api_key=PARTNER_KEY, server_secret=SERVER_SECRET
        )
        box = await ReturnBoxService.create(
            s, label="Box", api_key=DEVICE_KEY, server_secret=SERVER_SECRET
        )
        await s.commit()
        return p.id, box.id


async def _walk_to_deposited(
    api_client: AsyncClient,
    *,
    cleaning_center: uuid.UUID,
    cleaning_actor: uuid.UUID,
    restaurant: uuid.UUID,
    restaurant_actor: uuid.UUID,
    courier: uuid.UUID,
    box_id: uuid.UUID,
    asset_count: int = 1,
) -> tuple[list[dict], str]:
    """Returns (asset_list_with_token, consumer_id)."""
    cleaning_headers = {
        "X-Role": "cleaning_center",
        "X-Actor-Id": str(cleaning_actor),
        "X-Organization-Id": str(cleaning_center),
    }
    restaurant_headers = {
        "X-Role": "restaurant",
        "X-Actor-Id": str(restaurant_actor),
        "X-Organization-Id": str(restaurant),
    }
    courier_headers = {"X-Role": "courier", "X-Actor-Id": str(courier)}

    create = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": "meal_box", "count": asset_count},
        headers=cleaning_headers,
    )
    assets = create.json()["created"]
    asset_ids = [a["id"] for a in assets]
    await api_client.post(
        "/cleaning/assets/prepare-for-dispatch",
        json={"asset_ids": asset_ids},
        headers=cleaning_headers,
    )
    dispatch = await api_client.post(
        "/cleaning/dispatches",
        json={"restaurant_id": str(restaurant), "asset_ids": asset_ids, "note": None},
        headers=cleaning_headers,
    )
    await api_client.post(
        f"/restaurant/dispatches/{dispatch.json()['id']}/acknowledge",
        headers=restaurant_headers,
    )
    order = await api_client.post(
        "/partner/orders",
        json={
            "external_order_id": f"o-{uuid.uuid4().hex[:8]}",
            "restaurant_id": str(restaurant),
            "courier_id": str(courier),
            "external_consumer_ref": f"c-{uuid.uuid4().hex[:8]}",
            "expected_asset_manifest": {"meal_box": asset_count},
        },
        headers={"X-Partner-Api-Key": PARTNER_KEY},
    )
    order_body = order.json()

    pickup = await api_client.post(
        f"/courier/orders/{order_body['order_id']}/pickup-sessions",
        headers=courier_headers,
    )
    session_id = pickup.json()["pickup_session_id"]
    for asset in assets:
        await api_client.post(
            f"/courier/pickup-sessions/{session_id}/scan",
            json={"asset_token": asset["asset_token"]},
            headers=courier_headers,
        )
    await api_client.post(f"/courier/pickup-sessions/{session_id}/confirm", headers=courier_headers)
    await api_client.post(
        f"/courier/orders/{order_body['order_id']}/deliver",
        json={"pin": order_body["delivery_pin"]},
        headers=courier_headers,
    )

    consumer_id = order_body["consumer_id"]
    for asset in assets:
        await api_client.post(
            "/consumer/returns/scan",
            json={"asset_token": asset["asset_token"], "return_box_id": str(box_id)},
            headers={"X-Role": "consumer", "X-Actor-Id": consumer_id},
        )
        await api_client.post(
            f"/devices/return-boxes/{box_id}/sensor-events",
            json={
                "device_event_id": f"e-{uuid.uuid4().hex[:6]}",
                "event_type": "micro_switch_triggered",
                "triggered_at": datetime.now(UTC).isoformat(),
            },
            headers={"X-Device-Key": DEVICE_KEY},
        )
    return assets, consumer_id


@pytest.mark.asyncio
async def test_full_close_loop_releases_deposit_and_grants_reward(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    _, box_id = await _seed_partner_and_box(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    assets, _consumer_id = await _walk_to_deposited(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
        box_id=box_id,
        asset_count=1,
    )

    cleaning_headers = {
        "X-Role": "cleaning_center",
        "X-Actor-Id": str(cleaning_actor),
        "X-Organization-Id": str(cleaning_center),
    }
    receive = await api_client.post(
        "/cleaning/receive",
        json={"asset_tokens": [assets[0]["asset_token"]]},
        headers=cleaning_headers,
    )
    assert receive.status_code == 200, receive.text
    body = receive.json()
    assert body["received"][0]["deposit_outcome"] == "released"
    assert body["received"][0]["reward_granted"] is True
    assert body["received"][0]["reward_points"] == 5

    inspect = await api_client.post(
        "/cleaning/inspection",
        json={
            "asset_id": body["received"][0]["asset_id"],
            "condition": "usable",
            "component_status": {"lid": "ok", "chopsticks": "missing"},
            "notes": "minor",
        },
        headers=cleaning_headers,
    )
    assert inspect.status_code == 200
    assert inspect.json()["new_status"] == "washing"

    complete = await api_client.post(
        "/cleaning/washing-batches/complete",
        json={"asset_ids": [body["received"][0]["asset_id"]]},
        headers=cleaning_headers,
    )
    assert complete.status_code == 200

    async with sm() as db:
        consumer = (await db.execute(select(Consumer))).scalar_one()
        assert consumer.wallet_balance == 1000  # refunded
        assert consumer.points == 5
        assert consumer.deposit_level == 0

        deposits = (await db.execute(select(DepositRecord))).scalars().all()
        assert len(deposits) == 1
        assert deposits[0].status == DepositStatus.RELEASED
        assert deposits[0].released_at is not None

        rewards = (await db.execute(select(RewardTransaction))).scalars().all()
        assert len(rewards) == 1
        assert rewards[0].points == 5

        rs = (await db.execute(select(ReturnSession))).scalar_one()
        assert rs.status == ReturnSessionStatus.CONFIRMED_BY_CLEANING_CENTER

        asset = (await db.execute(select(Asset))).scalar_one()
        assert asset.status.value == "cleaned_ready"
        assert asset.usage_count == 1
        assert asset.current_cycle_id is None
        assert asset.last_washed_at is not None

        cycle = (await db.execute(select(AssetCycle))).scalar_one()
        assert cycle.status == CycleStatus.COMPLETED
        assert cycle.ended_at is not None

        for required in (
            AssetEventType.CLEANING_CENTER_RECEIVED,
            AssetEventType.DEPOSIT_RELEASED,
            AssetEventType.REWARD_GRANTED,
            AssetEventType.ASSET_MARKED_READY,
        ):
            count = (
                (await db.execute(select(AssetEvent).where(AssetEvent.event_type == required)))
                .scalars()
                .all()
            )
            assert len(count) >= 1, f"missing event {required.value}"


@pytest.mark.asyncio
async def test_late_return_charges_deposit_and_skips_reward(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    _, box_id = await _seed_partner_and_box(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    assets, _ = await _walk_to_deposited(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
        box_id=box_id,
        asset_count=1,
    )

    # Backdate the deposit so the cleaning confirmation falls past due_at.
    async with sm() as db:
        deposit = (await db.execute(select(DepositRecord))).scalar_one()
        far_past = datetime.now(UTC) - timedelta(days=40)
        deposit.borrowed_at = far_past
        deposit.reward_cutoff_at = far_past + timedelta(days=14)
        deposit.due_at = far_past + timedelta(days=31)
        db.add(deposit)
        await db.commit()

    cleaning_headers = {
        "X-Role": "cleaning_center",
        "X-Actor-Id": str(cleaning_actor),
        "X-Organization-Id": str(cleaning_center),
    }
    receive = await api_client.post(
        "/cleaning/receive",
        json={"asset_tokens": [assets[0]["asset_token"]]},
        headers=cleaning_headers,
    )
    assert receive.status_code == 200
    body = receive.json()
    assert body["received"][0]["deposit_outcome"] == "charged"
    assert body["received"][0]["reward_granted"] is False

    async with sm() as db:
        consumer = (await db.execute(select(Consumer))).scalar_one()
        assert consumer.wallet_balance == 800  # NOT refunded
        assert consumer.points == 0
        assert consumer.deposit_level == 1
        assert consumer.current_required_deposit == 300
        assert consumer.overdue_count == 1

        deposits = (await db.execute(select(DepositRecord))).scalars().all()
        assert deposits[0].status == DepositStatus.CHARGED


@pytest.mark.asyncio
async def test_inspection_can_mark_damaged_or_retired(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    _, box_id = await _seed_partner_and_box(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    assets, _ = await _walk_to_deposited(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
        box_id=box_id,
        asset_count=1,
    )
    cleaning_headers = {
        "X-Role": "cleaning_center",
        "X-Actor-Id": str(cleaning_actor),
        "X-Organization-Id": str(cleaning_center),
    }
    receive = await api_client.post(
        "/cleaning/receive",
        json={"asset_tokens": [assets[0]["asset_token"]]},
        headers=cleaning_headers,
    )
    asset_id = receive.json()["received"][0]["asset_id"]

    inspect = await api_client.post(
        "/cleaning/inspection",
        json={"asset_id": asset_id, "condition": "damaged"},
        headers=cleaning_headers,
    )
    assert inspect.status_code == 200
    assert inspect.json()["new_status"] == "damaged"


@pytest.mark.asyncio
async def test_reward_unique_constraint_prevents_double_payout(
    api_client: AsyncClient,
    test_engine,
) -> None:
    """Direct DB attempt to insert a duplicate reward must fail on UNIQUE."""
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    _, box_id = await _seed_partner_and_box(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    assets, _ = await _walk_to_deposited(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
        box_id=box_id,
        asset_count=1,
    )
    cleaning_headers = {
        "X-Role": "cleaning_center",
        "X-Actor-Id": str(cleaning_actor),
        "X-Organization-Id": str(cleaning_center),
    }
    receive = await api_client.post(
        "/cleaning/receive",
        json={"asset_tokens": [assets[0]["asset_token"]]},
        headers=cleaning_headers,
    )
    asset_uuid = uuid.UUID(receive.json()["received"][0]["asset_id"])

    from app.core.ids import new_uuid7
    from app.domain.rewards.models import REWARD_REASON_RETURN, RewardStatus

    async with sm() as db:
        existing = (
            await db.execute(
                select(RewardTransaction).where(RewardTransaction.asset_id == asset_uuid)
            )
        ).scalar_one()
        dupe = RewardTransaction(
            id=new_uuid7(),
            consumer_id=existing.consumer_id,
            asset_id=existing.asset_id,
            cycle_id=existing.cycle_id,
            event_id=None,
            points=5,
            reason=REWARD_REASON_RETURN,
            status=RewardStatus.CONFIRMED,
            created_at=datetime.now(UTC),
        )
        db.add(dupe)
        from sqlalchemy.exc import IntegrityError

        with pytest.raises(IntegrityError):
            await db.commit()
