"""DELETE endpoint integration tests for admin onboarding routes.

Hard-delete: organizations, users, consumers (refused if FK refs exist).
Soft-delete: partners, return-boxes (active=false, idempotent).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient


def _admin_headers() -> dict[str, str]:
    return {"X-Role": "admin", "X-Actor-Id": str(uuid.uuid4())}


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_organization_happy_path(api_client: AsyncClient) -> None:
    headers = _admin_headers()
    create = await api_client.post(
        "/admin/organizations",
        headers=headers,
        json={"type": "cleaning_center", "name": "to-be-removed"},
    )
    assert create.status_code == 201, create.text
    org_id = create.json()["id"]

    delete = await api_client.delete(f"/admin/organizations/{org_id}", headers=headers)
    assert delete.status_code == 204, delete.text

    # idempotent: a second delete is also 204
    again = await api_client.delete(f"/admin/organizations/{org_id}", headers=headers)
    assert again.status_code == 204

    listed = await api_client.get("/admin/organizations", headers=headers)
    ids = [o["id"] for o in listed.json()]
    assert org_id not in ids


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_organization_blocked_when_user_references(
    api_client: AsyncClient,
) -> None:
    headers = _admin_headers()
    org = (
        await api_client.post(
            "/admin/organizations",
            headers=headers,
            json={"type": "cleaning_center", "name": "with-staff"},
        )
    ).json()
    user = (
        await api_client.post(
            "/admin/users",
            headers=headers,
            json={
                "role": "cleaning_staff",
                "label": "staff",
                "organization_id": org["id"],
            },
        )
    ).json()

    delete = await api_client.delete(f"/admin/organizations/{org['id']}", headers=headers)
    assert delete.status_code == 409
    detail = delete.json()["detail"]
    assert detail["references"]["users"] == 1

    # remove the user, then deletion succeeds
    rm_user = await api_client.delete(f"/admin/users/{user['id']}", headers=headers)
    assert rm_user.status_code == 204

    delete2 = await api_client.delete(f"/admin/organizations/{org['id']}", headers=headers)
    assert delete2.status_code == 204


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_user_idempotent(api_client: AsyncClient) -> None:
    headers = _admin_headers()
    user = (
        await api_client.post(
            "/admin/users",
            headers=headers,
            json={"role": "courier", "label": "tmp"},
        )
    ).json()
    user_id = user["id"]

    first = await api_client.delete(f"/admin/users/{user_id}", headers=headers)
    second = await api_client.delete(f"/admin/users/{user_id}", headers=headers)
    assert first.status_code == 204
    assert second.status_code == 204


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_consumer_blocked_when_holding(
    api_client: AsyncClient,
) -> None:
    headers = _admin_headers()
    consumer = (
        await api_client.post("/admin/consumers", headers=headers, json={"label": "with-holding"})
    ).json()

    # Manually attach a partner_consumers row so the FK guard fires; this is
    # simpler than walking the full delivery flow here.
    from datetime import UTC, datetime

    from app.domain.consumers.models import PartnerConsumer

    # use a side connection so we don't fight with the test transaction
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from tests.integration.conftest import TEST_URL

    side_engine = create_async_engine(TEST_URL)
    sm = async_sessionmaker(bind=side_engine, class_=AsyncSession, expire_on_commit=False)
    async with sm() as session:
        session.add(
            PartnerConsumer(
                partner_id=uuid.uuid4(),
                external_ref="ext-1",
                consumer_id=uuid.UUID(consumer["id"]),
                created_at=datetime.now(UTC),
            )
        )
        await session.commit()
    await side_engine.dispose()

    blocked = await api_client.delete(f"/admin/consumers/{consumer['id']}", headers=headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["references"]["partner_links"] == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_partner_soft_delete(api_client: AsyncClient) -> None:
    headers = _admin_headers()
    partner = (
        await api_client.post("/admin/partners", headers=headers, json={"name": "soft-del"})
    ).json()
    partner_id = partner["id"]
    assert partner["active"] is True

    first = await api_client.delete(f"/admin/partners/{partner_id}", headers=headers)
    assert first.status_code == 200
    assert first.json()["active"] is False

    # idempotent
    second = await api_client.delete(f"/admin/partners/{partner_id}", headers=headers)
    assert second.status_code == 200
    assert second.json()["active"] is False

    # filter by include_inactive=false hides it
    listed = await api_client.get("/admin/partners?include_inactive=false", headers=headers)
    assert all(p["id"] != partner_id for p in listed.json())
    listed_all = await api_client.get("/admin/partners?include_inactive=true", headers=headers)
    assert any(p["id"] == partner_id for p in listed_all.json())


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_return_box_soft_delete(api_client: AsyncClient) -> None:
    headers = _admin_headers()
    box = (
        await api_client.post("/admin/return-boxes", headers=headers, json={"label": "rb-temp"})
    ).json()
    box_id = box["id"]
    assert box["active"] is True

    first = await api_client.delete(f"/admin/return-boxes/{box_id}", headers=headers)
    assert first.status_code == 200
    assert first.json()["active"] is False

    second = await api_client.delete(f"/admin/return-boxes/{box_id}", headers=headers)
    assert second.status_code == 200


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_partner_404_for_unknown_id(api_client: AsyncClient) -> None:
    headers = _admin_headers()
    res = await api_client.delete(f"/admin/partners/{uuid.uuid4()}", headers=headers)
    assert res.status_code == 404


@pytest.mark.asyncio(loop_scope="session")
async def test_delete_requires_admin_role(api_client: AsyncClient) -> None:
    res = await api_client.delete(
        f"/admin/organizations/{uuid.uuid4()}",
        headers={"X-Role": "courier", "X-Actor-Id": str(uuid.uuid4())},
    )
    assert res.status_code == 403
