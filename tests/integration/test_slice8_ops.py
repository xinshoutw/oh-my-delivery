"""Slice 8 — notifications, chain anchor, dashboard."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.domain.deposits.models import DepositRecord
from app.domain.devices.service import ReturnBoxService
from app.domain.hashchain.anchor_models import ChainAnchor
from app.domain.notifications.models import (
    Notification,
    NotificationStatus,
    NotificationType,
)
from app.domain.notifications.service import NotificationService
from app.domain.partners.service import PartnerService
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PARTNER_KEY = "ops-key"
DEVICE_KEY = "ops-device"
SERVER_SECRET = "x" * 32


async def _seed(sm: async_sessionmaker[AsyncSession]) -> tuple[uuid.UUID, uuid.UUID]:
    async with sm() as s:
        p = await PartnerService.create(
            s, name="P", api_key=PARTNER_KEY, server_secret=SERVER_SECRET
        )
        b = await ReturnBoxService.create(
            s, label="Box", api_key=DEVICE_KEY, server_secret=SERVER_SECRET
        )
        await s.commit()
        return p.id, b.id


async def _walk_to_with_consumer(
    api_client: AsyncClient,
    *,
    cleaning_center: uuid.UUID,
    cleaning_actor: uuid.UUID,
    restaurant: uuid.UUID,
    restaurant_actor: uuid.UUID,
    courier: uuid.UUID,
    asset_count: int = 1,
) -> dict:
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
    sid = pickup.json()["pickup_session_id"]
    for a in assets:
        await api_client.post(
            f"/courier/pickup-sessions/{sid}/scan",
            json={"asset_token": a["asset_token"]},
            headers=courier_headers,
        )
    await api_client.post(f"/courier/pickup-sessions/{sid}/confirm", headers=courier_headers)
    await api_client.post(
        f"/courier/orders/{order_body['order_id']}/deliver",
        json={"pin": order_body["delivery_pin"]},
        headers=courier_headers,
    )
    return order_body


@pytest.mark.asyncio
async def test_delivery_schedules_four_reminder_notifications(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed(sm)

    await _walk_to_with_consumer(
        api_client,
        cleaning_center=uuid.uuid4(),
        cleaning_actor=uuid.uuid4(),
        restaurant=uuid.uuid4(),
        restaurant_actor=uuid.uuid4(),
        courier=uuid.uuid4(),
    )

    async with sm() as db:
        deposit = (await db.execute(select(DepositRecord))).scalar_one()
        notes = (
            (
                await db.execute(
                    select(Notification).where(Notification.deposit_record_id == deposit.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(notes) == 4
        types = {n.notification_type for n in notes}
        assert types == {
            NotificationType.RETURN_REMINDER_DAY_7,
            NotificationType.RETURN_REMINDER_DAY_14,
            NotificationType.RETURN_REMINDER_DAY_21,
            NotificationType.RETURN_REMINDER_LAST_DAY,
        }
        for n in notes:
            assert n.status == NotificationStatus.PENDING
            assert n.scheduled_at > datetime.now(UTC)


@pytest.mark.asyncio
async def test_dispatch_marks_due_notifications_sent(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed(sm)

    await _walk_to_with_consumer(
        api_client,
        cleaning_center=uuid.uuid4(),
        cleaning_actor=uuid.uuid4(),
        restaurant=uuid.uuid4(),
        restaurant_actor=uuid.uuid4(),
        courier=uuid.uuid4(),
    )

    async with sm() as db:
        deposit = (await db.execute(select(DepositRecord))).scalar_one()
        deposit_id = deposit.id
        deposit.borrowed_at = datetime.now(UTC) - timedelta(days=8)
        db.add(deposit)
        notes = (
            (
                await db.execute(
                    select(Notification).where(Notification.deposit_record_id == deposit_id)
                )
            )
            .scalars()
            .all()
        )
        for n in notes:
            n.scheduled_at = datetime.now(UTC) - timedelta(minutes=5)
            db.add(n)
        await db.commit()

    async with sm() as db:
        await NotificationService.dispatch_due(db, limit=200)
        await db.commit()

    async with sm() as db:
        notes_after = (
            (
                await db.execute(
                    select(Notification).where(Notification.deposit_record_id == deposit_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(notes_after) == 4
        assert all(n.status == NotificationStatus.SENT for n in notes_after)
        assert all(n.sent_at is not None for n in notes_after)


@pytest.mark.asyncio
async def test_compute_chain_anchor_via_admin_endpoint(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed(sm)

    await _walk_to_with_consumer(
        api_client,
        cleaning_center=uuid.uuid4(),
        cleaning_actor=uuid.uuid4(),
        restaurant=uuid.uuid4(),
        restaurant_actor=uuid.uuid4(),
        courier=uuid.uuid4(),
    )

    admin_headers = {"X-Role": "admin", "X-Actor-Id": str(uuid.uuid4())}
    response = await api_client.post(
        "/admin/chain-anchors/compute?anchor_for_yesterday=false",
        headers=admin_headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["event_count"] >= 1
    assert len(body["root_hash"]) == 64

    # Re-running same day is idempotent (returns same root).
    response2 = await api_client.post(
        "/admin/chain-anchors/compute?anchor_for_yesterday=false",
        headers=admin_headers,
    )
    assert response2.status_code == 200
    assert response2.json()["root_hash"] == body["root_hash"]

    async with sm() as db:
        anchors = (await db.execute(select(ChainAnchor))).scalars().all()
        assert len(anchors) == 1


@pytest.mark.asyncio
async def test_dashboard_returns_meaningful_summary(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed(sm)

    await _walk_to_with_consumer(
        api_client,
        cleaning_center=uuid.uuid4(),
        cleaning_actor=uuid.uuid4(),
        restaurant=uuid.uuid4(),
        restaurant_actor=uuid.uuid4(),
        courier=uuid.uuid4(),
        asset_count=2,
    )

    admin_headers = {"X-Role": "admin", "X-Actor-Id": str(uuid.uuid4())}
    response = await api_client.get("/admin/dashboard", headers=admin_headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_assets"] == 2
    assert body["assets_by_status"].get("with_consumer", 0) == 2
    assert body["active_deposits"] == 2
    assert body["total_orders"] == 1
    assert body["orders_by_status"].get("delivered", 0) == 1
    assert body["active_cycles"] == 2
    assert body["total_consumers"] == 1


@pytest.mark.asyncio
async def test_dispatch_idempotent_after_send(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    await _seed(sm)
    await _walk_to_with_consumer(
        api_client,
        cleaning_center=uuid.uuid4(),
        cleaning_actor=uuid.uuid4(),
        restaurant=uuid.uuid4(),
        restaurant_actor=uuid.uuid4(),
        courier=uuid.uuid4(),
    )

    async with sm() as db:
        deposit = (await db.execute(select(DepositRecord))).scalar_one()
        deposit_id = deposit.id
        notes = (
            (
                await db.execute(
                    select(Notification).where(Notification.deposit_record_id == deposit_id)
                )
            )
            .scalars()
            .all()
        )
        for n in notes:
            n.scheduled_at = datetime.now(UTC) - timedelta(minutes=5)
            db.add(n)
        await db.commit()

    async with sm() as db:
        await NotificationService.dispatch_due(db, limit=200)
        await db.commit()
    async with sm() as db:
        await NotificationService.dispatch_due(db, limit=200)
        await db.commit()

    async with sm() as db:
        sent_count = (
            (
                await db.execute(
                    select(Notification).where(
                        Notification.deposit_record_id == deposit_id,
                        Notification.status == NotificationStatus.SENT,
                    )
                )
            )
            .scalars()
            .all()
        )
        pending_count = (
            (
                await db.execute(
                    select(Notification).where(
                        Notification.deposit_record_id == deposit_id,
                        Notification.status == NotificationStatus.PENDING,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(sent_count) == 4
        assert len(pending_count) == 0
