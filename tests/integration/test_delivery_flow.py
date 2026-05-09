"""PIN delivery → consumer takes responsibility, deposit records created."""

from __future__ import annotations

import uuid

import pytest
from app.domain.assets.models import Asset, AssetEventType
from app.domain.consumers.models import Consumer
from app.domain.delivery.models import DeliveryPinAttempt
from app.domain.deposits.models import DepositRecord, DepositStatus
from app.domain.orders.models import Order, OrderStatus
from app.domain.partners.service import PartnerService
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PARTNER_KEY = "delivery-test-key"
SERVER_SECRET = "x" * 32


async def _seed_partner(sm: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sm() as session:
        partner = await PartnerService.create(
            session, name="P", api_key=PARTNER_KEY, server_secret=SERVER_SECRET
        )
        await session.commit()
        return partner.id


async def _walk_to_picked_up(
    api_client: AsyncClient,
    *,
    cleaning_center: uuid.UUID,
    cleaning_actor: uuid.UUID,
    restaurant: uuid.UUID,
    restaurant_actor: uuid.UUID,
    courier: uuid.UUID,
    asset_count: int = 1,
) -> tuple[str, str]:
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

    order_response = await api_client.post(
        "/partner/orders",
        json={
            "external_order_id": f"ord-{uuid.uuid4().hex[:8]}",
            "restaurant_id": str(restaurant),
            "courier_id": str(courier),
            "external_consumer_ref": f"u-{uuid.uuid4().hex[:8]}",
            "expected_asset_manifest": {"meal_box": asset_count},
        },
        headers={"X-Partner-Api-Key": PARTNER_KEY},
    )
    order_body = order_response.json()
    order_id = order_body["order_id"]
    pin = order_body["delivery_pin"]

    pickup_response = await api_client.post(
        f"/courier/orders/{order_id}/pickup-sessions",
        headers=courier_headers,
    )
    session_id = pickup_response.json()["pickup_session_id"]
    for asset in assets:
        await api_client.post(
            f"/courier/pickup-sessions/{session_id}/scan",
            json={"asset_token": asset["asset_token"]},
            headers=courier_headers,
        )
    await api_client.post(
        f"/courier/pickup-sessions/{session_id}/confirm",
        headers=courier_headers,
    )
    return order_id, pin


@pytest.mark.asyncio
async def test_correct_pin_transfers_to_consumer_and_freezes_wallet(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_partner(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    order_id, pin = await _walk_to_picked_up(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
        asset_count=2,
    )

    response = await api_client.post(
        f"/courier/orders/{order_id}/deliver",
        json={"pin": pin},
        headers={"X-Role": "courier", "X-Actor-Id": str(courier)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "delivered"
    assert len(body["delivered_assets"]) == 2

    async with sm() as db:
        order = (await db.execute(select(Order))).scalar_one()
        assert order.status == OrderStatus.DELIVERED
        assert order.delivered_at is not None
        assert order.delivery_pin_hash is None  # cleared on success

        deposits = (await db.execute(select(DepositRecord))).scalars().all()
        assert len(deposits) == 2
        for d in deposits:
            assert d.status == DepositStatus.ACTIVE
            assert d.amount == 200

        consumer = (await db.execute(select(Consumer))).scalar_one()
        assert consumer.wallet_balance == 1000 - 2 * 200  # initial 1000 - 2 deposits

        assets = (await db.execute(select(Asset))).scalars().all()
        for asset in assets:
            assert asset.status.value == "with_consumer"
            assert asset.physical_holder_id == consumer.id

        attempts = (await db.execute(select(DeliveryPinAttempt))).scalars().all()
        assert len(attempts) == 1
        assert attempts[0].success is True

        from app.domain.assets.models import AssetEvent

        delivered_events = (
            await db.execute(
                select(AssetEvent.event_type).where(
                    AssetEvent.event_type.in_(
                        [
                            AssetEventType.ASSET_DELIVERED_TO_CONSUMER,
                            AssetEventType.DELIVERY_PIN_VERIFIED,
                        ]
                    )
                )
            )
        ).all()
        assert len(delivered_events) == 4  # 2 events x 2 assets


@pytest.mark.asyncio
async def test_wrong_pin_increments_failed_count(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_partner(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    order_id, _real_pin = await _walk_to_picked_up(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
    )

    courier_headers = {"X-Role": "courier", "X-Actor-Id": str(courier)}
    response = await api_client.post(
        f"/courier/orders/{order_id}/deliver",
        json={"pin": "000000"},
        headers=courier_headers,
    )
    assert response.status_code == 401
    body = response.json()
    assert body["status"] == "wrong_pin"
    assert body["remaining_attempts"] == 4
    assert body["support_required"] is False

    async with sm() as db:
        order = (await db.execute(select(Order))).scalar_one()
        assert order.pin_failed_count == 1
        assert order.status == OrderStatus.PICKED_UP


@pytest.mark.asyncio
async def test_pin_locks_after_5_failed_attempts(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_partner(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    order_id, real_pin = await _walk_to_picked_up(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
    )

    courier_headers = {"X-Role": "courier", "X-Actor-Id": str(courier)}
    last_response = None
    for _ in range(5):
        last_response = await api_client.post(
            f"/courier/orders/{order_id}/deliver",
            json={"pin": "999999"},
            headers=courier_headers,
        )
    assert last_response is not None
    assert last_response.status_code == 401
    body = last_response.json()
    assert body["status"] == "pin_locked"
    assert body["support_required"] is True

    async with sm() as db:
        order = (await db.execute(select(Order))).scalar_one()
        assert order.status == OrderStatus.PIN_LOCKED

    # Even the real PIN should be rejected once locked.
    response = await api_client.post(
        f"/courier/orders/{order_id}/deliver",
        json={"pin": real_pin},
        headers=courier_headers,
    )
    assert response.status_code == 401
    assert response.json()["status"] == "pin_locked"


@pytest.mark.asyncio
async def test_deliver_rejects_wrong_courier(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_partner(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier_a = uuid.uuid4()
    courier_b = uuid.uuid4()

    order_id, pin = await _walk_to_picked_up(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier_a,
    )
    response = await api_client.post(
        f"/courier/orders/{order_id}/deliver",
        json={"pin": pin},
        headers={"X-Role": "courier", "X-Actor-Id": str(courier_b)},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_correct_pin_records_pin_attempts_audit(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_partner(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    order_id, pin = await _walk_to_picked_up(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
    )

    headers = {"X-Role": "courier", "X-Actor-Id": str(courier)}
    # 2 failures + 1 success
    await api_client.post(
        f"/courier/orders/{order_id}/deliver", json={"pin": "111111"}, headers=headers
    )
    await api_client.post(
        f"/courier/orders/{order_id}/deliver", json={"pin": "222222"}, headers=headers
    )
    success_response = await api_client.post(
        f"/courier/orders/{order_id}/deliver", json={"pin": pin}, headers=headers
    )
    assert success_response.status_code == 200

    async with sm() as db:
        attempts = (await db.execute(select(DeliveryPinAttempt))).scalars().all()
        assert len(attempts) == 3
        assert sum(1 for a in attempts if not a.success) == 2
        assert sum(1 for a in attempts if a.success) == 1
