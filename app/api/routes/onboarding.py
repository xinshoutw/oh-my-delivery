"""Demo onboarding routes: admin can create orgs/users/return-boxes/partners/consumers/orders.

These endpoints make the demo navigable without forcing operators to type UUIDs.
They are deliberately admin-only because they shortcut authentication (e.g. the
caller chooses which partner to mock-create an order for).
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Actor, get_db_session, require_role
from app.core.config import get_settings
from app.core.ids import new_uuid7
from app.domain.assets.enums import ActorRole, AssetType, HolderType
from app.domain.assets.models import Asset
from app.domain.consumers.models import Consumer, PartnerConsumer
from app.domain.deposits.models import DepositRecord
from app.domain.devices.models import ReturnBox
from app.domain.devices.service import ReturnBoxService
from app.domain.dispatches.models import Dispatch
from app.domain.notifications.models import Notification
from app.domain.orders.models import Order
from app.domain.orders.schemas import CreateOrderResponse
from app.domain.orders.service import OrderService
from app.domain.organizations.models import OrganizationType
from app.domain.organizations.service import OrganizationService
from app.domain.partners.models import Partner
from app.domain.partners.service import PartnerService
from app.domain.users.models import User, UserRole
from app.domain.users.service import UserService

router = APIRouter(prefix="/admin", tags=["admin-onboarding"])


# --- Organizations -----------------------------------------------------------


class CreateOrganizationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: OrganizationType
    name: str = Field(min_length=1, max_length=128)


class OrganizationOut(BaseModel):
    id: uuid.UUID
    type: OrganizationType
    name: str
    created_at: datetime


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
async def create_organization(
    body: CreateOrganizationBody,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> OrganizationOut:
    org = await OrganizationService.create(session, type_=body.type, name=body.name)
    return OrganizationOut(id=org.id, type=org.type, name=org.name, created_at=org.created_at)


@router.get("/organizations", response_model=list[OrganizationOut])
async def list_organizations(
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
    type: OrganizationType | None = Query(default=None),
) -> Sequence[OrganizationOut]:
    items = await OrganizationService.list_all(session, type_=type)
    return [
        OrganizationOut(id=o.id, type=o.type, name=o.name, created_at=o.created_at) for o in items
    ]


# --- Users (admin / staff / courier / recycler) ------------------------------


class CreateUserBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: UserRole
    label: str = Field(min_length=1, max_length=128)
    organization_id: uuid.UUID | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    role: UserRole
    label: str
    organization_id: uuid.UUID | None
    created_at: datetime


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: CreateUserBody,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> UserOut:
    if (
        body.role in {UserRole.CLEANING_STAFF, UserRole.RESTAURANT_STAFF}
        and body.organization_id is None
    ):
        raise HTTPException(status_code=400, detail="staff role requires organization_id")
    if body.organization_id is not None:
        org = await OrganizationService.get(session, body.organization_id)
        if org is None:
            raise HTTPException(status_code=404, detail="organization not found")
        if body.role == UserRole.CLEANING_STAFF and org.type != OrganizationType.CLEANING_CENTER:
            raise HTTPException(
                status_code=400, detail="cleaning_staff requires cleaning_center org"
            )
        if body.role == UserRole.RESTAURANT_STAFF and org.type != OrganizationType.RESTAURANT:
            raise HTTPException(status_code=400, detail="restaurant_staff requires restaurant org")
    user = await UserService.create(
        session, role=body.role, label=body.label, organization_id=body.organization_id
    )
    return UserOut(
        id=user.id,
        role=user.role,
        label=user.label,
        organization_id=user.organization_id,
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
    role: UserRole | None = Query(default=None),
    organization_id: uuid.UUID | None = Query(default=None),
) -> Sequence[UserOut]:
    items = await UserService.list_all(session, role=role, organization_id=organization_id)
    return [
        UserOut(
            id=u.id,
            role=u.role,
            label=u.label,
            organization_id=u.organization_id,
            created_at=u.created_at,
        )
        for u in items
    ]


# --- Consumers ---------------------------------------------------------------


class CreateConsumerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=128)
    email: str | None = Field(default=None, max_length=256)
    phone: str | None = Field(default=None, max_length=32)


class ConsumerOut(BaseModel):
    id: uuid.UUID
    label: str
    email: str | None
    phone: str | None
    wallet_balance: int
    points: int
    deposit_level: int


@router.post("/consumers", response_model=ConsumerOut, status_code=201)
async def create_consumer(
    body: CreateConsumerBody,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> ConsumerOut:
    consumer = Consumer(
        id=new_uuid7(),
        email=body.email,
        phone=body.phone,
        deposit_level=0,
        current_required_deposit=200,
        overdue_count=0,
        wallet_balance=0,
        points=0,
        created_at=datetime.now(UTC),
    )
    session.add(consumer)
    await session.flush()
    return ConsumerOut(
        id=consumer.id,
        label=body.label,
        email=consumer.email,
        phone=consumer.phone,
        wallet_balance=consumer.wallet_balance,
        points=consumer.points,
        deposit_level=consumer.deposit_level,
    )


@router.get("/consumers", response_model=list[ConsumerOut])
async def list_consumers(
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
    limit: int = Query(default=200, ge=1, le=1000),
) -> Sequence[ConsumerOut]:
    rows = (
        (await session.execute(select(Consumer).order_by(Consumer.created_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return [
        ConsumerOut(
            id=c.id,
            label=c.email or c.phone or str(c.id)[:8],
            email=c.email,
            phone=c.phone,
            wallet_balance=c.wallet_balance,
            points=c.points,
            deposit_level=c.deposit_level,
        )
        for c in rows
    ]


# --- Partners -----------------------------------------------------------------


class CreatePartnerBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)


class PartnerOut(BaseModel):
    id: uuid.UUID
    name: str
    active: bool
    created_at: datetime


class PartnerCreatedOut(PartnerOut):
    api_key: str


@router.post("/partners", response_model=PartnerCreatedOut, status_code=201)
async def create_partner(
    body: CreatePartnerBody,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> PartnerCreatedOut:
    settings = get_settings()
    api_key = "pk_" + secrets.token_urlsafe(24)
    partner = await PartnerService.create(
        session, name=body.name, api_key=api_key, server_secret=settings.server_secret
    )
    return PartnerCreatedOut(
        id=partner.id,
        name=partner.name,
        active=partner.active,
        created_at=partner.created_at,
        api_key=api_key,
    )


@router.get("/partners", response_model=list[PartnerOut])
async def list_partners(
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
    include_inactive: bool = Query(default=True),
) -> Sequence[PartnerOut]:
    stmt = select(Partner).order_by(Partner.created_at.desc())
    if not include_inactive:
        stmt = stmt.where(Partner.active.is_(True))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        PartnerOut(id=p.id, name=p.name, active=p.active, created_at=p.created_at) for p in rows
    ]


# --- Return boxes ------------------------------------------------------------


class CreateReturnBoxBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=128)


class ReturnBoxOut(BaseModel):
    id: uuid.UUID
    label: str
    active: bool
    created_at: datetime


class ReturnBoxCreatedOut(ReturnBoxOut):
    api_key: str


@router.post("/return-boxes", response_model=ReturnBoxCreatedOut, status_code=201)
async def create_return_box(
    body: CreateReturnBoxBody,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> ReturnBoxCreatedOut:
    settings = get_settings()
    api_key = "rb_" + secrets.token_urlsafe(24)
    box = await ReturnBoxService.create(
        session, label=body.label, api_key=api_key, server_secret=settings.server_secret
    )
    return ReturnBoxCreatedOut(
        id=box.id,
        label=box.label,
        active=box.active,
        created_at=box.created_at,
        api_key=api_key,
    )


@router.get("/return-boxes", response_model=list[ReturnBoxOut])
async def list_return_boxes(
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
    include_inactive: bool = Query(default=True),
) -> Sequence[ReturnBoxOut]:
    stmt = select(ReturnBox).order_by(ReturnBox.created_at.desc())
    if not include_inactive:
        stmt = stmt.where(ReturnBox.active.is_(True))
    rows = (await session.execute(stmt)).scalars().all()
    return [
        ReturnBoxOut(id=b.id, label=b.label, active=b.active, created_at=b.created_at) for b in rows
    ]


# --- Demo order creation -----------------------------------------------------


class DemoOrderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    partner_id: uuid.UUID
    restaurant_id: uuid.UUID
    courier_id: uuid.UUID
    consumer_id: uuid.UUID
    external_order_id: str | None = Field(default=None, max_length=128)
    expected_asset_manifest: dict[AssetType, int]


@router.post("/demo-orders", response_model=CreateOrderResponse, status_code=201)
async def create_demo_order(
    body: DemoOrderBody,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> CreateOrderResponse:
    partner = await PartnerService.get(session, body.partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="partner not found")
    consumer = (
        await session.execute(select(Consumer).where(Consumer.id == body.consumer_id))
    ).scalar_one_or_none()
    if consumer is None:
        raise HTTPException(status_code=404, detail="consumer not found")

    external_ref = body.external_order_id or f"demo-{uuid.uuid4().hex[:12]}"

    # Pre-link the chosen consumer to (partner, external_ref) so OrderService
    # picks up the same consumer instead of upserting a brand-new one.
    from app.domain.consumers.models import PartnerConsumer

    existing_link = (
        await session.execute(
            select(PartnerConsumer).where(
                PartnerConsumer.partner_id == partner.id,
                PartnerConsumer.external_ref == external_ref,
            )
        )
    ).scalar_one_or_none()
    if existing_link is None:
        link = PartnerConsumer(
            partner_id=partner.id,
            external_ref=external_ref,
            consumer_id=consumer.id,
            created_at=datetime.now(UTC),
        )
        session.add(link)
        await session.flush()
    elif existing_link.consumer_id != consumer.id:
        raise HTTPException(
            status_code=409,
            detail="external_order_id already linked to a different consumer",
        )

    order, pin = await OrderService.create(
        session,
        partner_id=partner.id,
        external_order_id=external_ref,
        restaurant_id=body.restaurant_id,
        courier_id=body.courier_id,
        external_consumer_ref=external_ref,
        expected_asset_manifest=body.expected_asset_manifest,
        consumer_email=None,
        consumer_phone=None,
        consumer_national_id_hash=None,
    )
    assert order.delivery_pin_expires_at is not None
    return CreateOrderResponse(
        order_id=order.id,
        external_order_id=order.external_order_id,
        consumer_id=order.consumer_id,
        status=order.status,
        delivery_pin=pin,
        delivery_pin_expires_at=order.delivery_pin_expires_at,
        expected_asset_manifest=order.expected_asset_manifest,
        created_at=order.created_at,
    )


# --- DELETE handlers --------------------------------------------------------
#
# Hard delete is allowed only on rows with no immutable-ledger references.
# Partners and return-boxes are soft-deleted (active=false) because they own a
# unique api_key_hash and historical orders / sensor_events still point at them.
# Anything that is part of the asset / cycle / event / hash-chain is *not*
# deletable — those are append-only by design (CLAUDE.md §13 #11).


async def _scalar_count(session: AsyncSession, stmt) -> int:
    result = await session.execute(stmt)
    row = result.first()
    return int(row[0]) if row else 0


@router.delete("/organizations/{org_id}", status_code=204)
async def delete_organization(
    org_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> None:
    org = await OrganizationService.get(session, org_id)
    if org is None:
        return  # idempotent

    user_count = await _scalar_count(
        session,
        select(func.count()).select_from(User).where(User.organization_id == org_id),
    )
    dispatch_count = await _scalar_count(
        session,
        select(func.count())
        .select_from(Dispatch)
        .where((Dispatch.cleaning_center_id == org_id) | (Dispatch.restaurant_id == org_id)),
    )
    order_count = await _scalar_count(
        session,
        select(func.count()).select_from(Order).where(Order.restaurant_id == org_id),
    )
    holder_type = (
        HolderType.CLEANING_CENTER
        if org.type == OrganizationType.CLEANING_CENTER
        else HolderType.RESTAURANT
    )
    asset_count = await _scalar_count(
        session,
        select(func.count())
        .select_from(Asset)
        .where((Asset.physical_holder_type == holder_type) & (Asset.physical_holder_id == org_id)),
    )

    refs = {
        "users": user_count,
        "dispatches": dispatch_count,
        "orders": order_count,
        "assets": asset_count,
    }
    if any(refs.values()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "organization has references; cannot delete", "references": refs},
        )

    await session.delete(org)
    await session.flush()


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> None:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        return  # idempotent
    # actor_id refs in asset_events / audit_logs are intentionally loose:
    # ledger rows survive even if the staff account is removed.
    await session.delete(user)
    await session.flush()


@router.delete("/consumers/{consumer_id}", status_code=204)
async def delete_consumer(
    consumer_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> None:
    consumer = (
        await session.execute(select(Consumer).where(Consumer.id == consumer_id))
    ).scalar_one_or_none()
    if consumer is None:
        return  # idempotent

    deposit_count = await _scalar_count(
        session,
        select(func.count())
        .select_from(DepositRecord)
        .where(DepositRecord.consumer_id == consumer_id),
    )
    order_count = await _scalar_count(
        session,
        select(func.count()).select_from(Order).where(Order.consumer_id == consumer_id),
    )
    holding_count = await _scalar_count(
        session,
        select(func.count())
        .select_from(Asset)
        .where(
            (Asset.physical_holder_type == HolderType.CONSUMER)
            & (Asset.physical_holder_id == consumer_id)
        ),
    )
    notification_count = await _scalar_count(
        session,
        select(func.count())
        .select_from(Notification)
        .where(Notification.consumer_id == consumer_id),
    )
    partner_link_count = await _scalar_count(
        session,
        select(func.count())
        .select_from(PartnerConsumer)
        .where(PartnerConsumer.consumer_id == consumer_id),
    )

    refs = {
        "deposits": deposit_count,
        "orders": order_count,
        "holdings": holding_count,
        "notifications": notification_count,
        "partner_links": partner_link_count,
    }
    if any(refs.values()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"message": "consumer has references; cannot delete", "references": refs},
        )

    await session.delete(consumer)
    await session.flush()


@router.delete("/partners/{partner_id}", status_code=200, response_model=PartnerOut)
async def delete_partner(
    partner_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> PartnerOut:
    """Soft-delete: marks partner inactive. Idempotent."""
    partner = await PartnerService.get(session, partner_id)
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="partner not found")
    if partner.active:
        partner.active = False
        session.add(partner)
        await session.flush()
    return PartnerOut(
        id=partner.id, name=partner.name, active=partner.active, created_at=partner.created_at
    )


@router.delete("/return-boxes/{box_id}", status_code=200, response_model=ReturnBoxOut)
async def delete_return_box(
    box_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    _actor: Actor = Depends(require_role(ActorRole.ADMIN)),
) -> ReturnBoxOut:
    """Soft-delete: marks return-box inactive. Idempotent."""
    box = (
        await session.execute(select(ReturnBox).where(ReturnBox.id == box_id))
    ).scalar_one_or_none()
    if box is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="return-box not found")
    if box.active:
        box.active = False
        session.add(box)
        await session.flush()
    return ReturnBoxOut(id=box.id, label=box.label, active=box.active, created_at=box.created_at)
