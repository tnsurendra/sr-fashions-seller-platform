"""Authenticated status, cancellation and constrained return processing."""
from decimal import Decimal
import time
from sqlalchemy import select
from app.models import Inventory, Seller, Store, ProductVariant
from app.ondc.models import (ONDCOrder, ONDCOrderItem, OrderStateEvent, FinancialEvent,
                             ReturnRequest)
from app.ondc.models import ProductPublicationRow
from app.ondc.protocol.errors import DiscoveryError
from app.ondc.protocol.replay import existing, accept
from app.ondc.protocol.purchase import callback_context
from app.ondc.signing.security import authenticate
from app.ondc.validators.discovery import require_fresh_context
from app.ondc.schemas.post_order import return_values
from app.ondc.utils.validation import duration_seconds

PROTOCOL_ORDER = {"accepted": "Accepted", "packed": "In-progress", "ready_for_pickup": "In-progress",
                  "picked_up": "In-progress", "delivered": "Completed", "cancelled": "Cancelled",
                  "fulfillment_failed": "In-progress"}
PROTOCOL_FULFILLMENT = {"accepted": "Pending", "packed": "Packed", "ready_for_pickup": "Packed",
                       "picked_up": "Order-picked-up", "delivered": "Order-delivered",
                       "cancelled": "Cancelled", "fulfillment_failed": "Delivery-failed"}
TRANSITIONS = {"accepted": {"packed", "cancelled", "fulfillment_failed"},
               "packed": {"ready_for_pickup", "picked_up", "cancelled", "fulfillment_failed"},
               "ready_for_pickup": {"picked_up", "cancelled", "fulfillment_failed"},
               "picked_up": {"delivered", "fulfillment_failed"},
               "fulfillment_failed": {"cancelled"}, "delivered": set(), "cancelled": set()}

def financial(db, order_id, key, event_type, status, amount, currency="INR", reference=None, detail=None):
    row = db.scalar(select(FinancialEvent).where(FinancialEvent.order_id == order_id,
                                                  FinancialEvent.idempotency_key == key))
    if row: return row
    row = FinancialEvent(order_id=order_id, idempotency_key=key, event_type=event_type, status=status,
        currency=currency, amount=Decimal(amount), transaction_reference=reference,
        occurred_at=time.time(), detail=detail or {})
    db.add(row)
    return row

def transition(db, order, target, *, key, actor, source, detail=None):
    prior = db.scalar(select(OrderStateEvent).where(OrderStateEvent.order_id == order.id,
                                                     OrderStateEvent.idempotency_key == key))
    if prior: return prior
    if target == order.internal_state:
        return None
    if target not in TRANSITIONS.get(order.internal_state, set()):
        raise ValueError("Invalid order state transition")
    before = order.internal_state
    order.internal_state = target
    order.state = PROTOCOL_ORDER[target]
    order.fulfillment_state = PROTOCOL_FULFILLMENT[target]
    order.version += 1
    order.updated_at = time.time()
    event = OrderStateEvent(order_id=order.id, idempotency_key=key, from_state=before, to_state=target,
        fulfillment_state=order.fulfillment_state, actor=actor, source=source,
        occurred_at=order.updated_at, detail=detail or {})
    db.add(event)
    return event

def order_wire(db, order):
    items = db.scalars(select(ONDCOrderItem).where(ONDCOrderItem.order_id == order.id)).all()
    if not items: raise ValueError("Order items missing")
    store = db.get(Store, items[0].store_id)
    seller = db.get(Seller, store.seller_id)
    fulfillment = dict(order.fulfillment)
    fulfillment.update(state={"descriptor": {"code": order.fulfillment_state}})
    if order.internal_state == "ready_for_pickup":
        fulfillment["tags"] = [{"code": "state", "list": [{"code": "ready_to_ship", "value": "yes"}]}]
    item_total = sum((item.total_price for item in items), Decimal("0"))
    breakup = [{"@ondc/org/item_id": item.item_id, "@ondc/org/item_quantity": {"count": item.quantity},
                "title": item.item_id, "@ondc/org/title_type": "item",
                "price": {"currency": order.currency, "value": format(item.total_price, ".2f")},
                "item": {"price": {"currency": order.currency, "value": format(item.unit_price, ".2f")}}}
               for item in items]
    delivery = order.amount - item_total
    if delivery:
        breakup.append({"@ondc/org/item_id": fulfillment.get("id", "F1"), "title": "Delivery charges",
            "@ondc/org/title_type": "delivery", "price": {"currency": order.currency, "value": format(delivery, ".2f")}})
    result = {"id": order.id, "state": order.state,
        "provider": {"id": f"seller-{seller.id}", "locations": [{"id": f"store-{store.id}"}]},
        "items": [{"id": item.item_id, "fulfillment_id": fulfillment.get("id", "F1"),
                   "quantity": {"count": item.quantity}} for item in items],
        "billing": order.billing, "fulfillments": [fulfillment],
        "quote": {"price": {"currency": order.currency, "value": format(order.amount, ".2f")},
                  "breakup": breakup, "ttl": "P1D"}, "payment": order.payment,
        "created_at": _stamp(order.created_at), "updated_at": _stamp(order.updated_at)}
    return result

def _stamp(value):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

class PostOrderService:
    def __init__(self, settings, registry, client):
        self.settings, self.registry, self.client = settings, registry, client
    async def accept(self, db, request, raw, headers):
        try: require_fresh_context(request.context)
        except ValueError: raise DiscoveryError("30022", "Stale or invalid message timestamp") from None
        await authenticate(raw, request, headers, self.settings, self.registry)
        row = existing(db, request.context, raw)
        if row: return row.id
        callback = getattr(self, request.context.action)(db, request)
        return accept(db, request, raw, callback, self.settings).id
    async def dispatch(self, db, identity):
        from app.ondc.protocol.service import DiscoveryService
        await DiscoveryService(self.settings, self.registry, self.client).dispatch(db, identity)
    def owned(self, db, order_id, bap_id, lock=False):
        query = select(ONDCOrder).where(ONDCOrder.id == order_id)
        if lock: query = query.with_for_update()
        order = db.scalar(query)
        if order is None: raise DiscoveryError("30018", "Order not found")
        if order.bap_id != bap_id: raise DiscoveryError("30018", "Order not found")
        return order
    def status(self, db, request):
        order = self.owned(db, request.message.order_id, request.context.bap_id)
        return {"context": callback_context(request.context, self.settings, "on_status"),
                "message": {"order": order_wire(db, order)}}
    def cancel(self, db, request):
        order = self.owned(db, request.message.order_id, request.context.bap_id, lock=True)
        if order.internal_state in {"picked_up", "delivered"}:
            raise DiscoveryError("30014", "Cancellation is no longer eligible")
        fulfillment_id = order.fulfillment.get("id", "F1")
        if request.message.descriptor.short_desc != fulfillment_id:
            raise DiscoveryError("30012", "Invalid cancellation fulfillment")
        tat = order.fulfillment.get("@ondc/org/TAT")
        if tat is None or time.time() < order.created_at + float(duration_seconds(tat)):
            raise DiscoveryError("30014", "Fulfillment TAT has not been breached")
        if order.internal_state != "cancelled":
            transition(db, order, "cancelled", key="cancel:" + request.context.transaction_id,
                       actor=request.context.bap_id, source="protocol", detail={"reason_id": "006"})
            items = db.scalars(select(ONDCOrderItem).where(ONDCOrderItem.order_id == order.id)).all()
            if not order.inventory_restored:
                for item in items:
                    inventory = db.scalar(select(Inventory).where(Inventory.variant_id == item.variant_id,
                        Inventory.store_id == item.store_id).with_for_update())
                    inventory.quantity += item.quantity
                order.inventory_restored = True
            order.cancelled_at = time.time()
            financial(db, order.id, "cancel-charge:" + request.context.transaction_id,
                      "cancellation_charge", "expected", Decimal("0"))
            if order.payment.get("status") == "PAID":
                financial(db, order.id, "refund-obligation:" + request.context.transaction_id,
                          "refund_obligation", "expected", order.amount,
                          detail={"reason_id": "006", "actual_refund_not_issued": True})
        payload = order_wire(db, order)
        payload["cancellation"] = {"cancelled_by": request.context.bap_id, "reason": {"id": "006"}}
        return {"context": callback_context(request.context, self.settings, "on_cancel"), "message": {"order": payload}}
    def update(self, db, request):
        order = self.owned(db, request.message.order.id, request.context.bap_id, lock=True)
        if order.internal_state != "delivered": raise DiscoveryError("30005", "Return is not eligible")
        values, quantity = return_values(request)
        item = db.scalar(select(ONDCOrderItem).where(ONDCOrderItem.order_id == order.id,
                                                     ONDCOrderItem.item_id == values["item_id"]))
        if item is None or quantity > item.quantity: raise DiscoveryError("30005", "Invalid return quantity")
        variant = db.get(ProductVariant, item.variant_id)
        publication = db.get(ProductPublicationRow, variant.product_id)
        window = (publication.data if publication else {}).get("return_window")
        if not publication or not publication.data.get("returnable") or not window:
            raise DiscoveryError("30005", "Item is not returnable")
        delivered = db.scalar(select(OrderStateEvent).where(OrderStateEvent.order_id == order.id,
            OrderStateEvent.to_state == "delivered").order_by(OrderStateEvent.occurred_at.desc()))
        if delivered is None or time.time() > delivered.occurred_at + float(duration_seconds(window)):
            raise DiscoveryError("30005", "Return window expired")
        current = db.scalar(select(ReturnRequest).where(ReturnRequest.order_id == order.id,
                                                         ReturnRequest.request_id == values["id"]))
        if current is None:
            current = ReturnRequest(order_id=order.id, request_id=values["id"], item_id=item.item_id,
                quantity=quantity, reason_id="003", reason_description=values.get("reason_desc"),
                state="Return_Initiated", requested_at=time.time())
            db.add(current)
        payload = order_wire(db, order)
        payload["fulfillments"].append({"id": current.request_id, "type": "Return",
            "state": {"descriptor": {"code": current.state}}, "tags": [{"code": "return_request",
            "list": [{"code": k, "value": str(v)} for k, v in values.items()] +
                    [{"code": "initiated_by", "value": request.context.bap_id}]}]})
        return {"context": callback_context(request.context, self.settings, "on_update"), "message": {"order": payload}}

def validate_post_order_callback(payload):
    action = payload.get("context", {}).get("action")
    if action not in {"on_status", "on_cancel", "on_update"} or not isinstance(payload.get("message", {}).get("order"), dict):
        raise ValueError("Invalid post-order callback")
    return payload
