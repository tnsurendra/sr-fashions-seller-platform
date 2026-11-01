"""Seed one clearly synthetic ONDC lifecycle for UI/documentation demonstrations.

This does not simulate Registry, Buyer App signatures, callbacks, refunds, or external
interoperability. It only creates idempotent local persistence records using the sample
catalog so the administration UI can demonstrate its complete read model.
"""
import time
import sys
from pathlib import Path
from decimal import Decimal
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_engine
from app.models import Inventory, ProductVariant
from app.ondc.models import (
    CheckoutIntent, FinancialEvent, ONDCOrder, ONDCOrderItem,
    OrderStateEvent, ReturnRequest,
)

ORDER_ID = "DEMO-ONDC-ORDER-001"
TRANSACTION_ID = "demo-ondc-transaction-001"
SKU = "SR-SHIRT-BLUE-M"

with Session(get_engine()) as db:
    existing = db.get(ONDCOrder, ORDER_ID)
    if existing:
        print(f"SKIP existing synthetic demo order: {ORDER_ID}")
        raise SystemExit(0)

    variant = db.scalar(select(ProductVariant).where(ProductVariant.sku == SKU))
    if variant is None:
        raise SystemExit("Run scripts/seed_catalog.py before seeding the demo order")
    stock = db.scalar(select(Inventory).where(Inventory.variant_id == variant.id).with_for_update())
    if stock is None or stock.quantity < 1:
        raise SystemExit(f"At least one unit of {SKU} is required")

    now = time.time()
    checkout = CheckoutIntent(
        transaction_id=TRANSACTION_ID, bap_id="demo-buyer.invalid",
        provider_id="demo-sr-fashions", store_id=stock.store_id, state="confirmed",
        selection={"items": [{"id": SKU, "quantity": {"selected": {"count": 1}}}]},
        quote={"price": {"currency": "INR", "value": "1199.00"}},
        checkout={"demo": True, "notice": "Synthetic documentation record; no customer data"},
        expires_at=now + 86400,
    )
    db.add(checkout)
    db.flush()
    order = ONDCOrder(
        id=ORDER_ID, transaction_id=TRANSACTION_ID, checkout_id=checkout.id,
        bap_id="demo-buyer.invalid", state="Completed", amount=Decimal("1199.00"),
        currency="INR", internal_state="delivered", fulfillment_state="Order-delivered",
        fulfillment={"id": "DEMO-FULFILLMENT-001", "type": "Delivery", "demo": True},
        payment={"status": "PAID", "type": "ON-ORDER", "demo": True},
        billing={"demo": True, "notice": "No personal information stored"},
        created_at=now - 7200, updated_at=now - 900, version=5,
        inventory_restored=False,
    )
    db.add(order)
    db.flush()
    db.add(ONDCOrderItem(
        order_id=ORDER_ID, item_id=SKU, variant_id=variant.id, store_id=stock.store_id,
        quantity=1, unit_price=Decimal("1199.00"), total_price=Decimal("1199.00"),
    ))
    states = [
        ("pending", "accepted", "Pending", now - 7200),
        ("accepted", "packed", "Packed", now - 6000),
        ("packed", "ready_for_pickup", "Packed", now - 5400),
        ("ready_for_pickup", "picked_up", "Order-picked-up", now - 3600),
        ("picked_up", "delivered", "Order-delivered", now - 900),
    ]
    for index, (source, target, fulfillment, occurred) in enumerate(states, 1):
        db.add(OrderStateEvent(
            order_id=ORDER_ID, idempotency_key=f"demo-state-{index}",
            from_state=source, to_state=target, fulfillment_state=fulfillment,
            actor="demo-seeder", source="documentation", occurred_at=occurred,
            detail={"demo": True},
        ))
    for key, event_type, status, occurred in [
        ("demo-expected", "expected_payment", "EXPECTED", now - 7200),
        ("demo-recorded", "recorded_payment", "BUYER_REPORTED_PAID", now - 7100),
    ]:
        db.add(FinancialEvent(
            order_id=ORDER_ID, idempotency_key=key, event_type=event_type,
            status=status, currency="INR", amount=Decimal("1199.00"),
            transaction_reference=None, occurred_at=occurred,
            detail={"demo": True, "notice": "Not settlement confirmation"},
        ))
    db.add(ReturnRequest(
        order_id=ORDER_ID, request_id="DEMO-RETURN-001", item_id=SKU, quantity=1,
        reason_id="003", reason_description="Synthetic size/fit demonstration",
        state="Return_Approved", requested_at=now - 600, decided_at=now - 300,
    ))
    stock.quantity -= 1
    db.commit()
    print(f"CREATED synthetic demo order {ORDER_ID}; committed one unit of {SKU}")
