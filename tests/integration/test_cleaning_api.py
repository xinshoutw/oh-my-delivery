from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(api_client: AsyncClient) -> None:
    response = await api_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"


@pytest.mark.asyncio
async def test_create_assets_returns_one_time_tokens(api_client: AsyncClient) -> None:
    actor_id = uuid.uuid4()
    org_id = uuid.uuid4()
    response = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": "meal_box", "count": 2},
        headers={
            "X-Role": "cleaning_center",
            "X-Actor-Id": str(actor_id),
            "X-Organization-Id": str(org_id),
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert len(body["created"]) == 2
    for item in body["created"]:
        assert item["asset_type"] == "meal_box"
        assert item["status"] == "at_cleaning_center"
        assert item["asset_token"].startswith("R1A.")
        assert len(item["short_code"]) == 8


@pytest.mark.asyncio
async def test_create_assets_rejects_consumer_role(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": "drink_cup", "count": 1},
        headers={
            "X-Role": "consumer",
            "X-Actor-Id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_assets_requires_organization_header(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": "drink_cup", "count": 1},
        headers={
            "X-Role": "cleaning_center",
            "X-Actor-Id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_create_assets_validates_count(api_client: AsyncClient) -> None:
    response = await api_client.post(
        "/cleaning/assets",
        json={"asset_type": "meal_box", "count": 0},
        headers={
            "X-Role": "cleaning_center",
            "X-Actor-Id": str(uuid.uuid4()),
            "X-Organization-Id": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 422
