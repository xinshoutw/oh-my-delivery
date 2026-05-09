"""Seed a presentation-grade snapshot of the system.

Resets the database first, then writes data that looks like the system has
been running for a while: 2 cleaning centers, 4 restaurants, 1 partner,
multiple staff and couriers, 6 consumers, 3 return boxes, ~70 assets spread
across realistic statuses, plus a handful of in-flight dispatches and orders.

The seed walks the actual services so deposits, audit log, and per-asset hash
chain stay valid — `dashboard`, `lookup`, `lists/*` will all return coherent
numbers immediately.

Usage::

    uv run python scripts/seed_demo.py
    uv run python scripts/seed_demo.py --yes
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# Make `app` importable when invoked as `python scripts/seed_demo.py`.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.hashing import hmac_sha256_hex  # noqa: E402
from app.core.ids import new_uuid7  # noqa: E402
from app.domain.assets.enums import AssetType  # noqa: E402
from app.domain.assets.service import AssetService  # noqa: E402
from app.domain.consumers.models import Consumer  # noqa: E402
from app.domain.devices.models import ReturnBox  # noqa: E402
from app.domain.dispatches.service import DispatchService  # noqa: E402
from app.domain.organizations.models import Organization, OrganizationType  # noqa: E402
from app.domain.partners.models import Partner  # noqa: E402
from app.domain.users.models import User, UserRole  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from scripts.reset_data import truncate_all  # noqa: E402


def _build_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    user = os.environ.get("PG_USER", "omd")
    password = os.environ.get("PG_PASSWORD", "omd")
    host = os.environ.get("PG_HOST", "localhost")
    port = os.environ.get("PG_PORT", "5432")
    db = os.environ.get("PG_DB", "omd")
    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"


@dataclass
class SeedResult:
    admin_id: uuid.UUID
    partner_id: uuid.UUID
    partner_api_key: str
    return_box_keys: list[tuple[str, str]]  # (label, api_key)
    cleaning_centers: list[Organization]
    restaurants: list[Organization]
    couriers: list[User]
    consumers: list[Consumer]
    cleaned_ready_count: int
    in_transit_count: int
    at_restaurant_count: int
    pending_dispatches: int
    acknowledged_dispatches: int


CLEANING_CENTERS = [
    "中正環保清洗中心",
    "南港循環餐具站",
]
RESTAURANTS = [
    "好食堂台北車站店",
    "綠光便當忠孝店",
    "晴天食事大安店",
    "豐盛廚房信義店",
]
COURIER_NAMES = ["林大維", "陳怡君", "王宥廷", "黃柏霖", "張雅婷"]
CONSUMER_NAMES = [
    "demo-Alice",
    "demo-Bob",
    "demo-Charlie",
    "demo-Diana",
    "demo-Ethan",
    "demo-Felicia",
]
RETURN_BOX_LABELS = [
    "捷運中山站 1F 大廳",
    "台北 101 美食街 B1",
    "南港 CITYLINK 廣場",
]


# --- entity helpers ----------------------------------------------------------


async def create_org(session: AsyncSession, *, type_: OrganizationType, name: str) -> Organization:
    org = Organization(id=new_uuid7(), type=type_, name=name, created_at=datetime.now(UTC))
    session.add(org)
    await session.flush()
    return org


async def create_user(
    session: AsyncSession,
    *,
    role: UserRole,
    label: str,
    organization_id: uuid.UUID | None = None,
) -> User:
    user = User(
        id=new_uuid7(),
        role=role,
        label=label,
        organization_id=organization_id,
        created_at=datetime.now(UTC),
    )
    session.add(user)
    await session.flush()
    return user


async def create_consumer(session: AsyncSession, *, label: str) -> tuple[Consumer, str]:
    """Create a consumer; return (consumer, label) so callers can label them."""
    consumer = Consumer(
        id=new_uuid7(),
        email=None,
        phone=None,
        deposit_level=0,
        current_required_deposit=200,
        overdue_count=0,
        wallet_balance=0,
        points=0,
        created_at=datetime.now(UTC),
    )
    session.add(consumer)
    await session.flush()
    return consumer, label


async def create_partner(session: AsyncSession, *, name: str) -> tuple[Partner, str]:
    settings = get_settings()
    api_key = "pk_" + secrets.token_urlsafe(24)
    partner = Partner(
        id=new_uuid7(),
        name=name,
        api_key_hash=hmac_sha256_hex(api_key, settings.server_secret),
        active=True,
        created_at=datetime.now(UTC),
    )
    session.add(partner)
    await session.flush()
    return partner, api_key


async def create_return_box(session: AsyncSession, *, label: str) -> tuple[ReturnBox, str]:
    settings = get_settings()
    api_key = "rb_" + secrets.token_urlsafe(24)
    box = ReturnBox(
        id=new_uuid7(),
        label=label,
        api_key_hash=hmac_sha256_hex(api_key, settings.server_secret),
        active=True,
        created_at=datetime.now(UTC),
    )
    session.add(box)
    await session.flush()
    return box, api_key


# --- asset lifecycle helpers -------------------------------------------------


async def create_asset_batch(
    session: AsyncSession,
    *,
    asset_type: AssetType,
    count: int,
    cleaning_center_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> list[uuid.UUID]:
    items = await AssetService.create_assets(
        session,
        asset_type=asset_type,
        count=count,
        cleaning_center_id=cleaning_center_id,
        actor_id=actor_id,
    )
    return [it.id for it in items]


async def make_cleaned_ready(
    session: AsyncSession,
    *,
    asset_ids: list[uuid.UUID],
    cleaning_center_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    if not asset_ids:
        return
    await DispatchService.prepare_assets_for_dispatch(
        session,
        asset_ids=asset_ids,
        cleaning_center_id=cleaning_center_id,
        actor_id=actor_id,
    )


async def dispatch_to(
    session: AsyncSession,
    *,
    asset_ids: list[uuid.UUID],
    cleaning_center_id: uuid.UUID,
    restaurant_id: uuid.UUID,
    actor_id: uuid.UUID,
    note: str,
) -> uuid.UUID:
    dispatch = await DispatchService.create_dispatch(
        session,
        cleaning_center_id=cleaning_center_id,
        restaurant_id=restaurant_id,
        asset_ids=asset_ids,
        note=note,
        actor_id=actor_id,
    )
    return dispatch.id


async def ack_dispatch(
    session: AsyncSession,
    *,
    dispatch_id: uuid.UUID,
    restaurant_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> None:
    await DispatchService.acknowledge_dispatch(
        session,
        dispatch_id=dispatch_id,
        restaurant_id=restaurant_id,
        actor_id=actor_id,
    )


# --- main seed ---------------------------------------------------------------


async def seed(session: AsyncSession) -> SeedResult:
    # 1. Admin + partner
    admin = await create_user(session, role=UserRole.ADMIN, label="Demo Admin")
    partner, partner_api_key = await create_partner(session, name="Demo 外送 Co.")

    # 2. Organizations
    cleaning_centers = [
        await create_org(session, type_=OrganizationType.CLEANING_CENTER, name=name)
        for name in CLEANING_CENTERS
    ]
    restaurants = [
        await create_org(session, type_=OrganizationType.RESTAURANT, name=name)
        for name in RESTAURANTS
    ]

    # 3. Staff per organization
    cleaning_staff = []
    for cc in cleaning_centers:
        cleaning_staff.append(
            await create_user(
                session,
                role=UserRole.CLEANING_STAFF,
                label=f"{cc.name}・主管",
                organization_id=cc.id,
            )
        )
    for rest in restaurants:
        await create_user(
            session,
            role=UserRole.RESTAURANT_STAFF,
            label=f"{rest.name}・店長",
            organization_id=rest.id,
        )

    # 4. Couriers and recycler
    couriers = [
        await create_user(session, role=UserRole.COURIER, label=name) for name in COURIER_NAMES
    ]
    await create_user(session, role=UserRole.RECYCLER, label="回收車隊・小李")

    # 5. Consumers
    consumers: list[Consumer] = []
    for label in CONSUMER_NAMES:
        consumer, _ = await create_consumer(session, label=label)
        consumers.append(consumer)

    # 6. Return boxes (print API key for the first one only — that's the demo
    # device the user can authenticate as).
    return_box_keys: list[tuple[str, str]] = []
    for label in RETURN_BOX_LABELS:
        _, api_key = await create_return_box(session, label=label)
        return_box_keys.append((label, api_key))

    # 7. Assets per cleaning center: rich distribution across statuses.
    cleaned_ready = 0
    in_transit = 0
    at_restaurant = 0
    pending_dispatches = 0
    acknowledged_dispatches = 0

    # Center A — heavier flow
    cc_a = cleaning_centers[0]
    staff_a = cleaning_staff[0]
    a_meal = await create_asset_batch(
        session,
        asset_type=AssetType.MEAL_BOX,
        count=20,
        cleaning_center_id=cc_a.id,
        actor_id=staff_a.id,
    )
    a_drink = await create_asset_batch(
        session,
        asset_type=AssetType.DRINK_CUP,
        count=20,
        cleaning_center_id=cc_a.id,
        actor_id=staff_a.id,
    )

    # 25 of 40 → cleaned_ready
    a_ready_pool = a_meal[:13] + a_drink[:12]
    await make_cleaned_ready(
        session,
        asset_ids=a_ready_pool,
        cleaning_center_id=cc_a.id,
        actor_id=staff_a.id,
    )

    # 10 of those → dispatched + acked into restaurant 0
    a_acked = a_ready_pool[:10]
    d_id = await dispatch_to(
        session,
        asset_ids=a_acked,
        cleaning_center_id=cc_a.id,
        restaurant_id=restaurants[0].id,
        actor_id=staff_a.id,
        note="午餐尖峰補貨",
    )
    await ack_dispatch(
        session,
        dispatch_id=d_id,
        restaurant_id=restaurants[0].id,
        actor_id=cleaning_staff[0].id,
    )
    at_restaurant += 10
    acknowledged_dispatches += 1

    # 5 of those → dispatched, NOT acked → restaurant 1 sees待簽收
    a_pending = a_ready_pool[10:15]
    await dispatch_to(
        session,
        asset_ids=a_pending,
        cleaning_center_id=cc_a.id,
        restaurant_id=restaurants[1].id,
        actor_id=staff_a.id,
        note="晚餐補貨 (待簽收)",
    )
    in_transit += 5
    pending_dispatches += 1

    # 10 stay cleaned_ready (出貨頁可選)
    cleaned_ready += len(a_ready_pool) - 15  # = 10
    # 15 stay at_cleaning_center

    # Center B — lighter flow, just to show the dashboard isn't single-sourced
    cc_b = cleaning_centers[1]
    staff_b = cleaning_staff[1]
    b_meal = await create_asset_batch(
        session,
        asset_type=AssetType.MEAL_BOX,
        count=15,
        cleaning_center_id=cc_b.id,
        actor_id=staff_b.id,
    )
    b_drink = await create_asset_batch(
        session,
        asset_type=AssetType.DRINK_CUP,
        count=15,
        cleaning_center_id=cc_b.id,
        actor_id=staff_b.id,
    )
    b_ready_pool = b_meal[:8] + b_drink[:7]
    await make_cleaned_ready(
        session,
        asset_ids=b_ready_pool,
        cleaning_center_id=cc_b.id,
        actor_id=staff_b.id,
    )

    # 5 acked into restaurant 2
    b_acked = b_ready_pool[:5]
    d_id_b = await dispatch_to(
        session,
        asset_ids=b_acked,
        cleaning_center_id=cc_b.id,
        restaurant_id=restaurants[2].id,
        actor_id=staff_b.id,
        note="補貨",
    )
    await ack_dispatch(
        session,
        dispatch_id=d_id_b,
        restaurant_id=restaurants[2].id,
        actor_id=cleaning_staff[1].id,
    )
    at_restaurant += 5
    acknowledged_dispatches += 1

    # 5 pending into restaurant 3
    b_pending = b_ready_pool[5:10]
    await dispatch_to(
        session,
        asset_ids=b_pending,
        cleaning_center_id=cc_b.id,
        restaurant_id=restaurants[3].id,
        actor_id=staff_b.id,
        note="新門市首批配送 (待簽收)",
    )
    in_transit += 5
    pending_dispatches += 1

    # 5 stay cleaned_ready
    cleaned_ready += len(b_ready_pool) - 10  # = 5
    # 15 stay at_cleaning_center

    # 8. Demo orders for the courier待取餐 list. We use OrderService directly so
    # consumer / partner_consumer / PIN are all wired up correctly.
    from app.domain.orders.service import OrderService

    demo_pins: list[tuple[str, str]] = []
    for idx, (rest, courier, consumer) in enumerate(
        [
            (restaurants[0], couriers[0], consumers[0]),
            (restaurants[0], couriers[1], consumers[1]),
            (restaurants[2], couriers[2], consumers[2]),
        ]
    ):
        # Pre-link consumer to partner so OrderService.create reuses our row
        # instead of upserting a new one (the same trick admin demo-orders uses).
        from app.domain.consumers.models import PartnerConsumer

        external_ref = f"demo-{idx + 1:03d}"
        session.add(
            PartnerConsumer(
                partner_id=partner.id,
                external_ref=external_ref,
                consumer_id=consumer.id,
                created_at=datetime.now(UTC),
            )
        )
        await session.flush()
        order, pin = await OrderService.create(
            session,
            partner_id=partner.id,
            external_order_id=external_ref,
            restaurant_id=rest.id,
            courier_id=courier.id,
            external_consumer_ref=external_ref,
            expected_asset_manifest={AssetType.MEAL_BOX: 1, AssetType.DRINK_CUP: 1},
            consumer_email=None,
            consumer_phone=None,
            consumer_national_id_hash=None,
        )
        demo_pins.append((order.external_order_id, pin))

    return SeedResult(
        admin_id=admin.id,
        partner_id=partner.id,
        partner_api_key=partner_api_key,
        return_box_keys=return_box_keys,
        cleaning_centers=cleaning_centers,
        restaurants=restaurants,
        couriers=couriers,
        consumers=consumers,
        cleaned_ready_count=cleaned_ready,
        in_transit_count=in_transit,
        at_restaurant_count=at_restaurant,
        pending_dispatches=pending_dispatches,
        acknowledged_dispatches=acknowledged_dispatches,
    ), demo_pins  # type: ignore[return-value]


async def main_async(skip_confirm: bool) -> int:
    url = _build_url()
    safe = url.split("@", 1)[-1] if "@" in url else url
    print(f"target database: {safe}")
    if not skip_confirm:
        confirm = input("This will RESET and re-seed the demo data. Type 'seed' to continue: ")
        if confirm.strip() != "seed":
            print("aborted.")
            return 1

    print("[1/3] truncating all tables…")
    await truncate_all(url)

    print("[2/3] seeding demo data…")
    engine = create_async_engine(url)
    sm = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sm() as session:
            result, demo_pins = await seed(session)  # type: ignore[misc]
            await session.commit()
    finally:
        await engine.dispose()

    print("[3/3] done. Summary:\n")
    print(f"  cleaning centers : {len(result.cleaning_centers)}")
    print(f"  restaurants      : {len(result.restaurants)}")
    print(f"  couriers         : {len(result.couriers)}")
    print(f"  consumers        : {len(result.consumers)}")
    print(f"  return boxes     : {len(result.return_box_keys)}")
    print(f"  assets cleaned   : {result.cleaned_ready_count}")
    print(f"  assets in_transit: {result.in_transit_count}")
    print(f"  assets at_rest   : {result.at_restaurant_count}")
    print(f"  pending dispatch : {result.pending_dispatches}")
    print(f"  acked dispatch   : {result.acknowledged_dispatches}")
    print()
    print("Partner API key (one-time, save it):")
    print(f"  {result.partner_api_key}")
    print()
    print("Return-box API keys (one-time, save them):")
    for label, key in result.return_box_keys:
        print(f"  [{label}] {key}")
    print()
    print("Demo order PINs (paste into courier delivery flow):")
    for ext_id, pin in demo_pins:
        print(f"  {ext_id}: {pin}")
    print()
    print("Tip: open the web UI, login as 系統管理員 → Demo Admin to inspect everything.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset and seed presentation-grade demo data.")
    parser.add_argument("--yes", "-y", action="store_true")
    args = parser.parse_args()
    return asyncio.run(main_async(skip_confirm=args.yes))


if __name__ == "__main__":
    sys.exit(main())
