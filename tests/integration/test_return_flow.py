"""Consumer return scan + sensor-event matching."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.domain.assets.models import Asset, AssetEvent, AssetEventType
from app.domain.devices.models import SensorEvent
from app.domain.devices.service import ReturnBoxService
from app.domain.partners.service import PartnerService
from app.domain.returns.models import ReturnSession, ReturnSessionStatus
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

PARTNER_KEY = "return-test-key"
DEVICE_KEY = "return-box-001-device-key"
SERVER_SECRET = "x" * 32


async def _seed_partner_and_box(
    sm: async_sessionmaker[AsyncSession],
) -> tuple[uuid.UUID, uuid.UUID]:
    async with sm() as session:
        partner = await PartnerService.create(
            session, name="P", api_key=PARTNER_KEY, server_secret=SERVER_SECRET
        )
        box = await ReturnBoxService.create(
            session,
            label="Lobby Drop Box",
            api_key=DEVICE_KEY,
            server_secret=SERVER_SECRET,
        )
        await session.commit()
        return partner.id, box.id


async def _walk_to_with_consumer(
    api_client: AsyncClient,
    *,
    cleaning_center: uuid.UUID,
    cleaning_actor: uuid.UUID,
    restaurant: uuid.UUID,
    restaurant_actor: uuid.UUID,
    courier: uuid.UUID,
    asset_count: int = 1,
) -> list[dict]:
    """Returns the asset list (with token + short_code) once delivered."""
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
    await api_client.post(
        f"/courier/pickup-sessions/{session_id}/confirm",
        headers=courier_headers,
    )
    await api_client.post(
        f"/courier/orders/{order_body['order_id']}/deliver",
        json={"pin": order_body["delivery_pin"]},
        headers=courier_headers,
    )
    return [{**a, "consumer_id": order_body["consumer_id"]} for a in assets]


@pytest.mark.asyncio
async def test_full_return_flow_consumer_scan_then_sensor_match(
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

    delivered = await _walk_to_with_consumer(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
    )
    asset = delivered[0]
    consumer_id = asset["consumer_id"]

    # 1. Consumer scans for return.
    scan = await api_client.post(
        "/consumer/returns/scan",
        json={"asset_token": asset["asset_token"], "return_box_id": str(box_id)},
        headers={"X-Role": "consumer", "X-Actor-Id": consumer_id},
    )
    assert scan.status_code == 201, scan.text
    scan_body = scan.json()
    assert scan_body["is_current_holder"] is True
    assert scan_body["status"] == "scanned"
    assert scan_body["asset_public_code"] == asset["short_code"]
    return_session_id = scan_body["return_session_id"]

    # 2. Sensor event arrives.
    sensor = await api_client.post(
        f"/devices/return-boxes/{box_id}/sensor-events",
        json={
            "device_event_id": "evt-001",
            "event_type": "micro_switch_triggered",
            "triggered_at": datetime.now(UTC).isoformat(),
        },
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert sensor.status_code == 202, sensor.text
    sensor_body = sensor.json()
    assert sensor_body["duplicate"] is False
    assert sensor_body["matched_return_session_id"] == return_session_id

    async with sm() as db:
        rs = (await db.execute(select(ReturnSession))).scalar_one()
        assert rs.status == ReturnSessionStatus.DEPOSIT_DETECTED
        assert rs.deposit_detected_at is not None

        db_asset = (await db.execute(select(Asset))).scalar_one()
        assert db_asset.status.value == "deposited_in_return_box"
        assert str(db_asset.physical_holder_id) == str(box_id)
        assert str(db_asset.responsible_party_id) == consumer_id  # responsibility unchanged

        events_returned = (
            await db.execute(
                select(AssetEvent.event_type).where(
                    AssetEvent.event_type.in_(
                        [
                            AssetEventType.CONSUMER_RETURN_SCANNED,
                            AssetEventType.RETURN_BOX_DEPOSIT_DETECTED,
                        ]
                    )
                )
            )
        ).all()
        assert len(events_returned) == 2


@pytest.mark.asyncio
async def test_sensor_event_idempotent_on_device_event_id(
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

    delivered = await _walk_to_with_consumer(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
    )
    asset = delivered[0]

    await api_client.post(
        "/consumer/returns/scan",
        json={"asset_token": asset["asset_token"], "return_box_id": str(box_id)},
        headers={"X-Role": "consumer", "X-Actor-Id": asset["consumer_id"]},
    )

    triggered_at = datetime.now(UTC).isoformat()
    headers = {"X-Device-Key": DEVICE_KEY}
    payload = {
        "device_event_id": "dup-1",
        "event_type": "micro_switch_triggered",
        "triggered_at": triggered_at,
    }
    first = await api_client.post(
        f"/devices/return-boxes/{box_id}/sensor-events",
        json=payload,
        headers=headers,
    )
    second = await api_client.post(
        f"/devices/return-boxes/{box_id}/sensor-events",
        json=payload,
        headers=headers,
    )
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert first.json()["sensor_event_id"] == second.json()["sensor_event_id"]

    async with sm() as db:
        rows = (await db.execute(select(SensorEvent))).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_orphan_sensor_event_recorded_without_match(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    _, box_id = await _seed_partner_and_box(sm)

    response = await api_client.post(
        f"/devices/return-boxes/{box_id}/sensor-events",
        json={
            "device_event_id": "orphan-1",
            "event_type": "micro_switch_triggered",
            "triggered_at": datetime.now(UTC).isoformat(),
        },
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 202
    body = response.json()
    assert body["duplicate"] is False
    assert body["matched_return_session_id"] is None


@pytest.mark.asyncio
async def test_sensor_event_rejects_invalid_device_key(
    api_client: AsyncClient,
    test_engine,
) -> None:
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    _, box_id = await _seed_partner_and_box(sm)

    response = await api_client.post(
        f"/devices/return-boxes/{box_id}/sensor-events",
        json={
            "device_event_id": "x",
            "event_type": "micro_switch_triggered",
            "triggered_at": datetime.now(UTC).isoformat(),
        },
        headers={"X-Device-Key": "wrong-key"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_consumer_helps_someone_else_return(
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

    delivered = await _walk_to_with_consumer(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
    )
    asset = delivered[0]
    helper_consumer = uuid.uuid4()

    scan = await api_client.post(
        "/consumer/returns/scan",
        json={"asset_token": asset["asset_token"], "return_box_id": str(box_id)},
        headers={"X-Role": "consumer", "X-Actor-Id": str(helper_consumer)},
    )
    assert scan.status_code == 201
    body = scan.json()
    assert body["is_current_holder"] is False
    assert "original holder" in body["message"]


@pytest.mark.asyncio
async def test_cancel_return_session_rolls_asset_back(
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

    delivered = await _walk_to_with_consumer(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
    )
    asset = delivered[0]

    scan = await api_client.post(
        "/consumer/returns/scan",
        json={"asset_token": asset["asset_token"], "return_box_id": str(box_id)},
        headers={"X-Role": "consumer", "X-Actor-Id": asset["consumer_id"]},
    )
    return_session_id = scan.json()["return_session_id"]

    cancel = await api_client.post(
        f"/consumer/return-sessions/{return_session_id}/cancel",
        headers={"X-Role": "consumer", "X-Actor-Id": asset["consumer_id"]},
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == ReturnSessionStatus.CANCELLED.value

    async with sm() as db:
        db_asset = (await db.execute(select(Asset))).scalar_one()
        assert db_asset.status.value == "with_consumer"


@pytest.mark.asyncio
async def test_concurrent_scan_at_same_box_is_rejected(
    api_client: AsyncClient,
    test_engine,
) -> None:
    """Fix 1: only one active SCANNED session per box is allowed.

    Without this, the sensor matcher (which picks the most recent SCANNED
    session) could attribute one drop to the wrong asset when two consumers
    scan back-to-back at the same box.
    """
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    _, box_id = await _seed_partner_and_box(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    delivered = await _walk_to_with_consumer(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
        asset_count=2,
    )
    asset_a, asset_b = delivered[0], delivered[1]

    first = await api_client.post(
        "/consumer/returns/scan",
        json={"asset_token": asset_a["asset_token"], "return_box_id": str(box_id)},
        headers={"X-Role": "consumer", "X-Actor-Id": asset_a["consumer_id"]},
    )
    assert first.status_code == 201, first.text

    # Second consumer (or same consumer with a different asset) at the same box
    # should be blocked while the first session is still active.
    second = await api_client.post(
        "/consumer/returns/scan",
        json={"asset_token": asset_b["asset_token"], "return_box_id": str(box_id)},
        headers={"X-Role": "consumer", "X-Actor-Id": asset_b["consumer_id"]},
    )
    assert second.status_code == 409, second.text
    assert "another return is in progress" in second.json()["detail"]


@pytest.mark.asyncio
async def test_sensor_event_with_clock_skew_rejected(
    api_client: AsyncClient,
    test_engine,
) -> None:
    """Fix 3: triggered_at outside the allowed skew window is rejected."""
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    _, box_id = await _seed_partner_and_box(sm)

    far_past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    response = await api_client.post(
        f"/devices/return-boxes/{box_id}/sensor-events",
        json={
            "device_event_id": "skew-1",
            "event_type": "micro_switch_triggered",
            "triggered_at": far_past,
        },
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert response.status_code == 422
    assert "clock skew" in response.json()["detail"]


@pytest.mark.asyncio
async def test_sensor_event_does_not_lie_when_asset_not_pending(
    api_client: AsyncClient,
    test_engine,
) -> None:
    """Fix 2: if the matched session's asset isn't in return_pending_deposit
    (e.g., a concurrent cancel), the sensor event must NOT claim it recorded
    a deposit, and matched_return_session_id must be null.
    """
    sm = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    _, box_id = await _seed_partner_and_box(sm)

    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()
    courier = uuid.uuid4()

    delivered = await _walk_to_with_consumer(
        api_client,
        cleaning_center=cleaning_center,
        cleaning_actor=cleaning_actor,
        restaurant=restaurant,
        restaurant_actor=restaurant_actor,
        courier=courier,
    )
    asset = delivered[0]

    scan = await api_client.post(
        "/consumer/returns/scan",
        json={"asset_token": asset["asset_token"], "return_box_id": str(box_id)},
        headers={"X-Role": "consumer", "X-Actor-Id": asset["consumer_id"]},
    )
    return_session_id = scan.json()["return_session_id"]

    # Force the asset back to with_consumer via the cancel route so the next
    # sensor event will have no valid pending session at this box.
    await api_client.post(
        f"/consumer/return-sessions/{return_session_id}/cancel",
        headers={"X-Role": "consumer", "X-Actor-Id": asset["consumer_id"]},
    )

    sensor = await api_client.post(
        f"/devices/return-boxes/{box_id}/sensor-events",
        json={
            "device_event_id": "evt-skip-1",
            "event_type": "micro_switch_triggered",
            "triggered_at": datetime.now(UTC).isoformat(),
        },
        headers={"X-Device-Key": DEVICE_KEY},
    )
    assert sensor.status_code == 202
    body = sensor.json()
    assert body["deposit_recorded"] is False
    # No active SCANNED session remains, so matched is null and message is
    # the orphan path.
    assert body["matched_return_session_id"] is None
    assert "orphan" in body["message"]
