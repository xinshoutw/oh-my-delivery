"""End-to-end happy path: cleaning center creates → ready → dispatches → restaurant acks."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_dispatch_handoff(api_client: AsyncClient) -> None:
    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()
    restaurant_actor = uuid.uuid4()

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

    # 1. Create assets at cleaning center.
    response = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": "meal_box", "count": 3},
        headers=cleaning_headers,
    )
    assert response.status_code == 201, response.text
    asset_ids = [item["id"] for item in response.json()["created"]]

    # 2. Mark them ready (washing → cleaned_ready).
    response = await api_client.post(
        "/cleaning/assets/prepare-for-dispatch",
        json={"asset_ids": asset_ids},
        headers=cleaning_headers,
    )
    assert response.status_code == 200, response.text
    assert response.json()["prepared_count"] == 3

    # 3. Dispatch to restaurant.
    response = await api_client.post(
        "/cleaning/dispatches",
        json={
            "restaurant_id": str(restaurant),
            "asset_ids": asset_ids,
            "note": "lunch batch",
        },
        headers=cleaning_headers,
    )
    assert response.status_code == 201, response.text
    dispatch_body = response.json()
    assert dispatch_body["status"] == "pending"
    dispatch_id = dispatch_body["id"]

    # 4. Restaurant acknowledges receipt.
    response = await api_client.post(
        f"/restaurant/dispatches/{dispatch_id}/acknowledge",
        headers=restaurant_headers,
    )
    assert response.status_code == 200, response.text
    ack_body = response.json()
    assert ack_body["acknowledged_count"] == 3
    assert set(ack_body["asset_ids"]) == set(asset_ids)


@pytest.mark.asyncio
async def test_dispatch_rejects_assets_not_at_cleaning_center(api_client: AsyncClient) -> None:
    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant = uuid.uuid4()

    cleaning_headers = {
        "X-Role": "cleaning_center",
        "X-Actor-Id": str(cleaning_actor),
        "X-Organization-Id": str(cleaning_center),
    }

    response = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": "drink_cup", "count": 1},
        headers=cleaning_headers,
    )
    asset_ids = [item["id"] for item in response.json()["created"]]

    # Trying to dispatch without prepare-for-dispatch should fail (not cleaned_ready).
    response = await api_client.post(
        "/cleaning/dispatches",
        json={"restaurant_id": str(restaurant), "asset_ids": asset_ids, "note": None},
        headers=cleaning_headers,
    )
    assert response.status_code == 409, response.text


@pytest.mark.asyncio
async def test_acknowledge_rejects_wrong_restaurant(api_client: AsyncClient) -> None:
    cleaning_center = uuid.uuid4()
    cleaning_actor = uuid.uuid4()
    restaurant_a = uuid.uuid4()
    restaurant_b = uuid.uuid4()

    cleaning_headers = {
        "X-Role": "cleaning_center",
        "X-Actor-Id": str(cleaning_actor),
        "X-Organization-Id": str(cleaning_center),
    }
    response = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": "meal_box", "count": 1},
        headers=cleaning_headers,
    )
    asset_ids = [item["id"] for item in response.json()["created"]]

    await api_client.post(
        "/cleaning/assets/prepare-for-dispatch",
        json={"asset_ids": asset_ids},
        headers=cleaning_headers,
    )
    response = await api_client.post(
        "/cleaning/dispatches",
        json={"restaurant_id": str(restaurant_a), "asset_ids": asset_ids, "note": None},
        headers=cleaning_headers,
    )
    dispatch_id = response.json()["id"]

    response = await api_client.post(
        f"/restaurant/dispatches/{dispatch_id}/acknowledge",
        headers={
            "X-Role": "restaurant",
            "X-Actor-Id": str(uuid.uuid4()),
            "X-Organization-Id": str(restaurant_b),
        },
    )
    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_acknowledge_idempotency_blocks_double_ack(api_client: AsyncClient) -> None:
    cleaning_center = uuid.uuid4()
    restaurant = uuid.uuid4()

    cleaning_headers = {
        "X-Role": "cleaning_center",
        "X-Actor-Id": str(uuid.uuid4()),
        "X-Organization-Id": str(cleaning_center),
    }
    restaurant_headers = {
        "X-Role": "restaurant",
        "X-Actor-Id": str(uuid.uuid4()),
        "X-Organization-Id": str(restaurant),
    }

    response = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": "drink_cup", "count": 1},
        headers=cleaning_headers,
    )
    asset_ids = [item["id"] for item in response.json()["created"]]
    await api_client.post(
        "/cleaning/assets/prepare-for-dispatch",
        json={"asset_ids": asset_ids},
        headers=cleaning_headers,
    )
    response = await api_client.post(
        "/cleaning/dispatches",
        json={"restaurant_id": str(restaurant), "asset_ids": asset_ids, "note": None},
        headers=cleaning_headers,
    )
    dispatch_id = response.json()["id"]

    response = await api_client.post(
        f"/restaurant/dispatches/{dispatch_id}/acknowledge",
        headers=restaurant_headers,
    )
    assert response.status_code == 200

    response = await api_client.post(
        f"/restaurant/dispatches/{dispatch_id}/acknowledge",
        headers=restaurant_headers,
    )
    assert response.status_code == 409
