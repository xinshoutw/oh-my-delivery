"""Partner platform creates orders; system mints PIN, upserts consumers."""

from __future__ import annotations

import re
import uuid

import pytest
from app.core.hashing import hash_pin
from app.domain.consumers.models import Consumer, PartnerConsumer
from app.domain.orders.models import Order, OrderStatus
from app.domain.partners.service import PartnerService
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


@pytest.fixture
def server_secret() -> str:
    return "x" * 32


async def _seed_partner(
    sm: async_sessionmaker[AsyncSession],
    *,
    api_key: str,
    server_secret: str,
    name: str = "TestEats",
) -> uuid.UUID:
    async with sm() as session:
        partner = await PartnerService.create(
            session,
            name=name,
            api_key=api_key,
            server_secret=server_secret,
        )
        await session.commit()
        return partner.id


@pytest.mark.asyncio
async def test_create_order_mints_pin_and_creates_consumer(
    api_client: AsyncClient,
    test_engine,
    server_secret: str,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    api_key = "partner-api-key-abcdef-0001"
    await _seed_partner(sm, api_key=api_key, server_secret=server_secret)

    body = {
        "external_order_id": "platform_order_001",
        "restaurant_id": str(uuid.uuid4()),
        "courier_id": str(uuid.uuid4()),
        "external_consumer_ref": "platform_user_8821",
        "expected_asset_manifest": {"meal_box": 1, "drink_cup": 2},
        "consumer_email": "alice@example.com",
        "consumer_phone": "0912000000",
    }
    response = await api_client.post(
        "/partner/orders", json=body, headers={"X-Partner-Api-Key": api_key}
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert re.match(r"^\d{6}$", payload["delivery_pin"])
    assert payload["status"] == "created"
    assert payload["expected_asset_manifest"] == {"meal_box": 1, "drink_cup": 2}

    async with sm() as session:
        order = (await session.execute(select(Order))).scalar_one()
        assert order.delivery_pin_hash == hash_pin(payload["delivery_pin"])
        assert order.status == OrderStatus.CREATED
        assert order.pin_failed_count == 0

        consumer = (await session.execute(select(Consumer))).scalar_one()
        assert consumer.email == "alice@example.com"
        assert consumer.deposit_level == 0
        assert consumer.current_required_deposit == 200

        link = (await session.execute(select(PartnerConsumer))).scalar_one()
        assert link.external_ref == "platform_user_8821"
        assert link.consumer_id == consumer.id


@pytest.mark.asyncio
async def test_create_order_reuses_existing_consumer_for_same_external_ref(
    api_client: AsyncClient,
    test_engine,
    server_secret: str,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    api_key = "partner-api-key-abcdef-0002"
    await _seed_partner(sm, api_key=api_key, server_secret=server_secret)

    base = {
        "restaurant_id": str(uuid.uuid4()),
        "courier_id": str(uuid.uuid4()),
        "external_consumer_ref": "repeat_user",
        "expected_asset_manifest": {"meal_box": 1},
        "consumer_email": "bob@example.com",
    }

    headers = {"X-Partner-Api-Key": api_key}
    r1 = await api_client.post(
        "/partner/orders", json={"external_order_id": "ord-1", **base}, headers=headers
    )
    r2 = await api_client.post(
        "/partner/orders", json={"external_order_id": "ord-2", **base}, headers=headers
    )
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["consumer_id"] == r2.json()["consumer_id"]

    async with sm() as session:
        consumers = (await session.execute(select(Consumer))).scalars().all()
        assert len(consumers) == 1


@pytest.mark.asyncio
async def test_create_order_rejects_duplicate_external_order_id(
    api_client: AsyncClient,
    test_engine,
    server_secret: str,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    api_key = "partner-api-key-abcdef-0003"
    await _seed_partner(sm, api_key=api_key, server_secret=server_secret)

    headers = {"X-Partner-Api-Key": api_key}
    body = {
        "external_order_id": "dup-001",
        "restaurant_id": str(uuid.uuid4()),
        "courier_id": str(uuid.uuid4()),
        "external_consumer_ref": "u-1",
        "expected_asset_manifest": {"meal_box": 1},
    }
    r1 = await api_client.post("/partner/orders", json=body, headers=headers)
    r2 = await api_client.post("/partner/orders", json=body, headers=headers)
    assert r1.status_code == 201
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_create_order_rejects_invalid_api_key(api_client: AsyncClient) -> None:
    body = {
        "external_order_id": "x",
        "restaurant_id": str(uuid.uuid4()),
        "courier_id": str(uuid.uuid4()),
        "external_consumer_ref": "u",
        "expected_asset_manifest": {"meal_box": 1},
    }
    response = await api_client.post(
        "/partner/orders", json=body, headers={"X-Partner-Api-Key": "wrong-key"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_order_validates_manifest(
    api_client: AsyncClient,
    test_engine,
    server_secret: str,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    api_key = "partner-api-key-abcdef-0004"
    await _seed_partner(sm, api_key=api_key, server_secret=server_secret)

    response = await api_client.post(
        "/partner/orders",
        json={
            "external_order_id": "x",
            "restaurant_id": str(uuid.uuid4()),
            "courier_id": str(uuid.uuid4()),
            "external_consumer_ref": "u",
            "expected_asset_manifest": {},
        },
        headers={"X-Partner-Api-Key": api_key},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_partner_with_national_id_match_links_existing_consumer(
    api_client: AsyncClient,
    test_engine,
    server_secret: str,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    partner_a_key = "key-A"
    partner_b_key = "key-B"
    await _seed_partner(sm, api_key=partner_a_key, server_secret=server_secret, name="A")
    await _seed_partner(sm, api_key=partner_b_key, server_secret=server_secret, name="B")

    nid_hash = "a" * 64
    common = {
        "restaurant_id": str(uuid.uuid4()),
        "courier_id": str(uuid.uuid4()),
        "expected_asset_manifest": {"meal_box": 1},
        "consumer_national_id_hash": nid_hash,
    }
    r_a = await api_client.post(
        "/partner/orders",
        json={"external_order_id": "ord-A", "external_consumer_ref": "ref-A", **common},
        headers={"X-Partner-Api-Key": partner_a_key},
    )
    r_b = await api_client.post(
        "/partner/orders",
        json={"external_order_id": "ord-B", "external_consumer_ref": "ref-B", **common},
        headers={"X-Partner-Api-Key": partner_b_key},
    )
    assert r_a.status_code == 201
    assert r_b.status_code == 201
    assert r_a.json()["consumer_id"] == r_b.json()["consumer_id"]
