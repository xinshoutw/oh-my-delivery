"""End-to-end pickup scan session: courier scans each asset and confirms."""

from __future__ import annotations

import uuid

import pytest
from app.domain.assets.models import Asset, AssetEvent, AssetEventType
from app.domain.orders.models import OrderStatus
from app.domain.orders.order_assets import OrderAsset
from app.domain.partners.service import PartnerService
from app.domain.pickup.models import PickupScanItem, PickupSessionStatus
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PARTNER_KEY = "courier-test-partner-key"
SERVER_SECRET = "x" * 32


async def _seed_partner(sm: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with sm() as session:
        partner = await PartnerService.create(
            session, name="P", api_key=PARTNER_KEY, server_secret=SERVER_SECRET
        )
        await session.commit()
        return partner.id


async def _setup_assets_at_restaurant(
    api_client: AsyncClient,
    cleaning_center: uuid.UUID,
    cleaning_actor: uuid.UUID,
    restaurant: uuid.uuid4,
    restaurant_actor: uuid.UUID,
    asset_type: str,
    count: int,
) -> list[dict]:
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
    create = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": asset_type, "count": count},
        headers=cleaning_headers,
    )
    created = create.json()["created"]
    asset_ids = [a["id"] for a in created]
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
    dispatch_id = dispatch.json()["id"]
    await api_client.post(
        f"/restaurant/dispatches/{dispatch_id}/acknowledge",
        headers=restaurant_headers,
    )
    return created


async def _create_order(
    api_client: AsyncClient,
    *,
    restaurant: uuid.UUID,
    courier: uuid.UUID,
    manifest: dict[str, int],
) -> dict:
    response = await api_client.post(
        "/partner/orders",
        json={
            "external_order_id": f"ord-{uuid.uuid4().hex[:8]}",
            "restaurant_id": str(restaurant),
            "courier_id": str(courier),
            "external_consumer_ref": f"consumer-{uuid.uuid4().hex[:8]}",
            "expected_asset_manifest": manifest,
        },
        headers={"X-Partner-Api-Key": PARTNER_KEY},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_full_pickup_flow_meal_box_and_drink_cup(
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

    meal_assets = await _setup_assets_at_restaurant(
        api_client, cleaning_center, cleaning_actor, restaurant, restaurant_actor, "meal_box", 1
    )
    drink_assets = await _setup_assets_at_restaurant(
        api_client, cleaning_center, cleaning_actor, restaurant, restaurant_actor, "drink_cup", 2
    )

    order = await _create_order(
        api_client,
        restaurant=restaurant,
        courier=courier,
        manifest={"meal_box": 1, "drink_cup": 2},
    )
    order_id = order["order_id"]

    courier_headers = {
        "X-Role": "courier",
        "X-Actor-Id": str(courier),
    }

    response = await api_client.post(
        f"/courier/orders/{order_id}/pickup-sessions",
        headers=courier_headers,
    )
    assert response.status_code == 201
    session_id = response.json()["pickup_session_id"]

    for token_holder in (*meal_assets, *drink_assets):
        scan = await api_client.post(
            f"/courier/pickup-sessions/{session_id}/scan",
            json={"asset_token": token_holder["asset_token"]},
            headers=courier_headers,
        )
        assert scan.status_code == 200
        body = scan.json()
        assert body["accepted"] is True

    # Final scan should report fully_scanned.
    progress_response = await api_client.post(
        f"/courier/pickup-sessions/{session_id}/scan",
        json={"asset_token": meal_assets[0]["asset_token"]},
        headers=courier_headers,
    )
    assert progress_response.status_code == 200
    assert progress_response.json()["already_scanned"] is True

    confirm = await api_client.post(
        f"/courier/pickup-sessions/{session_id}/confirm",
        headers=courier_headers,
    )
    assert confirm.status_code == 200, confirm.text
    confirm_body = confirm.json()
    assert len(confirm_body["transferred_assets"]) == 3
    assert confirm_body["order_status"] == "picked_up"

    async with sm() as db:
        from app.domain.orders.models import Order

        db_order = (await db.execute(select(Order))).scalar_one()
        assert db_order.status == OrderStatus.PICKED_UP
        assert db_order.picked_up_at is not None

        order_assets = (await db.execute(select(OrderAsset))).scalars().all()
        assert len(order_assets) == 3

        events = (
            await db.execute(
                select(AssetEvent.event_type).where(
                    AssetEvent.event_type == AssetEventType.PICKUP_CONFIRMED_BY_COURIER
                )
            )
        ).all()
        assert len(events) == 3

        assets = (await db.execute(select(Asset))).scalars().all()
        for asset in assets:
            assert asset.status.value == "picked_by_courier"


@pytest.mark.asyncio
async def test_scan_rejects_wrong_type(
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

    meal = await _setup_assets_at_restaurant(
        api_client, cleaning_center, cleaning_actor, restaurant, restaurant_actor, "meal_box", 1
    )

    order = await _create_order(
        api_client,
        restaurant=restaurant,
        courier=courier,
        manifest={"drink_cup": 1},  # only drink_cup expected
    )
    courier_headers = {"X-Role": "courier", "X-Actor-Id": str(courier)}
    response = await api_client.post(
        f"/courier/orders/{order['order_id']}/pickup-sessions",
        headers=courier_headers,
    )
    session_id = response.json()["pickup_session_id"]

    scan = await api_client.post(
        f"/courier/pickup-sessions/{session_id}/scan",
        json={"asset_token": meal[0]["asset_token"]},
        headers=courier_headers,
    )
    assert scan.status_code == 200
    body = scan.json()
    assert body["accepted"] is False
    assert body["reject_reason"] == "asset_type_not_in_manifest"


@pytest.mark.asyncio
async def test_scan_rejects_unknown_token(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_partner(sm)

    restaurant = uuid.uuid4()
    courier = uuid.uuid4()

    order = await _create_order(
        api_client,
        restaurant=restaurant,
        courier=courier,
        manifest={"meal_box": 1},
    )
    courier_headers = {"X-Role": "courier", "X-Actor-Id": str(courier)}
    response = await api_client.post(
        f"/courier/orders/{order['order_id']}/pickup-sessions",
        headers=courier_headers,
    )
    session_id = response.json()["pickup_session_id"]

    scan = await api_client.post(
        f"/courier/pickup-sessions/{session_id}/scan",
        json={"asset_token": "R1A.NOPE0000000000"},
        headers=courier_headers,
    )
    assert scan.status_code == 200
    assert scan.json()["accepted"] is False
    assert scan.json()["reject_reason"] == "asset_not_found"


@pytest.mark.asyncio
async def test_confirm_rejects_incomplete_manifest(
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

    meal = await _setup_assets_at_restaurant(
        api_client, cleaning_center, cleaning_actor, restaurant, restaurant_actor, "meal_box", 2
    )
    order = await _create_order(
        api_client,
        restaurant=restaurant,
        courier=courier,
        manifest={"meal_box": 2},
    )
    courier_headers = {"X-Role": "courier", "X-Actor-Id": str(courier)}
    response = await api_client.post(
        f"/courier/orders/{order['order_id']}/pickup-sessions",
        headers=courier_headers,
    )
    session_id = response.json()["pickup_session_id"]

    await api_client.post(
        f"/courier/pickup-sessions/{session_id}/scan",
        json={"asset_token": meal[0]["asset_token"]},
        headers=courier_headers,
    )
    confirm = await api_client.post(
        f"/courier/pickup-sessions/{session_id}/confirm",
        headers=courier_headers,
    )
    assert confirm.status_code == 409
    assert "manifest incomplete" in confirm.json()["detail"]


@pytest.mark.asyncio
async def test_pickup_session_rejects_wrong_courier(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_partner(sm)

    restaurant = uuid.uuid4()
    courier_a = uuid.uuid4()
    courier_b = uuid.uuid4()

    order = await _create_order(
        api_client,
        restaurant=restaurant,
        courier=courier_a,
        manifest={"meal_box": 1},
    )
    response = await api_client.post(
        f"/courier/orders/{order['order_id']}/pickup-sessions",
        headers={"X-Role": "courier", "X-Actor-Id": str(courier_b)},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_short_code_fallback_works(
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

    meal = await _setup_assets_at_restaurant(
        api_client, cleaning_center, cleaning_actor, restaurant, restaurant_actor, "meal_box", 1
    )
    order = await _create_order(
        api_client,
        restaurant=restaurant,
        courier=courier,
        manifest={"meal_box": 1},
    )
    courier_headers = {"X-Role": "courier", "X-Actor-Id": str(courier)}
    response = await api_client.post(
        f"/courier/orders/{order['order_id']}/pickup-sessions",
        headers=courier_headers,
    )
    session_id = response.json()["pickup_session_id"]

    scan = await api_client.post(
        f"/courier/pickup-sessions/{session_id}/scan",
        json={"short_code": meal[0]["short_code"]},
        headers=courier_headers,
    )
    assert scan.status_code == 200
    assert scan.json()["accepted"] is True
    async with sm() as db:
        items = (await db.execute(select(PickupScanItem))).scalars().all()
        assert any(i.scan_method.value == "manual_short_code" for i in items)


@pytest.mark.asyncio
async def test_cancel_session_blocks_subsequent_scans(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed_partner(sm)

    restaurant = uuid.uuid4()
    courier = uuid.uuid4()

    order = await _create_order(
        api_client,
        restaurant=restaurant,
        courier=courier,
        manifest={"meal_box": 1},
    )
    courier_headers = {"X-Role": "courier", "X-Actor-Id": str(courier)}
    response = await api_client.post(
        f"/courier/orders/{order['order_id']}/pickup-sessions",
        headers=courier_headers,
    )
    session_id = response.json()["pickup_session_id"]

    cancel = await api_client.post(
        f"/courier/pickup-sessions/{session_id}/cancel",
        headers=courier_headers,
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == PickupSessionStatus.CANCELLED.value

    scan = await api_client.post(
        f"/courier/pickup-sessions/{session_id}/scan",
        json={"asset_token": "R1A.0000000000000000"},
        headers=courier_headers,
    )
    assert scan.status_code == 409
