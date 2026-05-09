"""Partner platform integration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_partner
from app.domain.orders.schemas import CreateOrderRequest, CreateOrderResponse
from app.domain.orders.service import OrderService
from app.domain.partners.models import Partner

router = APIRouter(prefix="/partner", tags=["partner"])


@router.post("/orders", response_model=CreateOrderResponse, status_code=201)
async def create_order(
    body: CreateOrderRequest,
    session: AsyncSession = Depends(get_db_session),
    partner: Partner = Depends(get_partner),
) -> CreateOrderResponse:
    order, pin = await OrderService.create(
        session,
        partner_id=partner.id,
        external_order_id=body.external_order_id,
        restaurant_id=body.restaurant_id,
        courier_id=body.courier_id,
        external_consumer_ref=body.external_consumer_ref,
        expected_asset_manifest=body.expected_asset_manifest,
        consumer_email=body.consumer_email,
        consumer_phone=body.consumer_phone,
        consumer_national_id_hash=body.consumer_national_id_hash,
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
