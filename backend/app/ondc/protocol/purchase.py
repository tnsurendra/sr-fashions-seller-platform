"""RET12 selection, checkout initialization and atomic confirmation service."""
from datetime import datetime, timezone
from decimal import Decimal
import time
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models import Inventory, ProductVariant, Product, Store, Seller
from app.ondc.models import (SellerPublication, CheckoutIntent, ONDCOrder, ONDCOrderItem,
                             OrderStateEvent, FinancialEvent)
from app.ondc.catalog.administration import load_profile
from app.ondc.protocol.errors import DiscoveryError
from app.ondc.protocol.replay import existing, accept
from app.ondc.signing.security import authenticate
from app.ondc.validators.discovery import require_fresh_context
from app.ondc.schemas.orders import money

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def callback_context(context, settings, action):
    data = context.to_wire()
    data.update(action=action, timestamp=stamp(), bpp_id=settings.subscriber_id,
                bpp_uri=settings.subscriber_url)
    data.pop("ttl", None)
    data.pop("key", None)
    return data

def item_parts(item_id):
    try:
        sku, store = item_id.rsplit("@store-", 1)
        return sku, int(store)
    except (ValueError, TypeError):
        raise DiscoveryError("30004", "Item not found") from None

class PurchaseService:
    def __init__(self, settings, registry, client):
        self.settings, self.registry, self.client = settings, registry, client

    async def accept(self, db, request, raw, headers):
        context = request.context
        if context.city not in ("*", self.settings.city):
            raise DiscoveryError("30008", "Location not serviceable")
        if context.bpp_id != self.settings.subscriber_id:
            raise DiscoveryError("30001", "Provider not found")
        try:
            require_fresh_context(context)
        except ValueError:
            raise DiscoveryError("30022", "Stale or invalid message timestamp") from None
        await authenticate(raw, request, headers, self.settings, self.registry)
        row = existing(db, context, raw)
        if row:
            return row.id
        callback = getattr(self, context.action)(db, request)
        row = accept(db, request, raw, callback, self.settings)
        return row.id

    async def dispatch(self, db, identity):
        from app.ondc.protocol.service import DiscoveryService
        await DiscoveryService(self.settings, self.registry, self.client).dispatch(db, identity)

    def provider(self, db, ref):
        rows = db.scalars(select(SellerPublication).where(SellerPublication.enabled.is_(True))).all()
        if len(rows) != 1 or ref.id != f"seller-{rows[0].seller_id}":
            raise DiscoveryError("30001", "Provider not found")
        seller = db.get(Seller, rows[0].seller_id)
        store_id = int(ref.locations[0].id.removeprefix("store-")) if ref.locations[0].id.startswith("store-") else -1
        store = db.get(Store, store_id)
        if store is None or store.seller_id != seller.id:
            raise DiscoveryError("30002", "Provider location not found")
        return seller, store, load_profile(db, seller.id)

    @staticmethod
    def cart(order):
        return {"provider": order.provider.to_wire(), "items": sorted([
            {"id": item.id, "count": item.quantity.count,
             "location_id": item.location_id or order.provider.locations[0].id}
            for item in order.items], key=lambda item: item["id"])}

    @staticmethod
    def stored_cart(data):
        location = data["provider"]["locations"][0]["id"]
        return {"provider": data["provider"], "items": sorted([
            {"id": item["id"], "count": item["quantity"]["count"],
             "location_id": item.get("location_id") or location}
            for item in data["items"]], key=lambda item: item["id"])}

    def resolve(self, db, order, *, lock=False):
        seller, store, profile = self.provider(db, order.provider)
        rows, subtotal = [], Decimal("0")
        seen = set()
        for requested in order.items:
            if requested.id in seen:
                raise DiscoveryError("30000", "Duplicate order item")
            seen.add(requested.id)
            sku, store_id = item_parts(requested.id)
            if store_id != store.id or requested.location_id not in (None, f"store-{store.id}"):
                raise DiscoveryError("30002", "Provider location not found")
            variant = db.scalar(select(ProductVariant).where(ProductVariant.sku == sku))
            if variant is None:
                raise DiscoveryError("30004", "Item not found")
            product = db.get(Product, variant.product_id)
            if product.seller_id != seller.id:
                raise DiscoveryError("30004", "Item not found")
            query = select(Inventory).where(Inventory.variant_id == variant.id, Inventory.store_id == store.id)
            if lock:
                query = query.with_for_update()
            inventory = db.scalar(query)
            maximum = profile.products[product.id].maximum_per_order
            if requested.quantity.count > maximum:
                raise DiscoveryError("40009", "Maximum order quantity exceeded")
            if inventory is None or inventory.quantity < requested.quantity.count:
                raise DiscoveryError("40002", "Item quantity unavailable")
            total = variant.selling_price * requested.quantity.count
            subtotal += total
            rows.append((requested, variant, product, inventory, total, maximum))
        store_meta = profile.stores[store.id]
        if store_meta.delivery_charge is None or store_meta.fulfillment_tat is None:
            raise DiscoveryError("40001", "Store purchase terms are not configured")
        destination = order.fulfillments[0].end.location.address.area_code
        serviceable = False
        for group in store_meta.tags:
            if group.code != "serviceability": continue
            values = {tag.code: tag.value for tag in group.list}
            if values.get("location") != f"store-{store.id}": continue
            serviceable |= values.get("type") == "12" and values.get("val") == "IND"
            serviceable |= values.get("type") == "11" and values.get("val") == destination
        if not serviceable:
            raise DiscoveryError("30009", "Delivery location not serviceable")
        delivery = money(store_meta.delivery_charge)
        return seller, store, profile, rows, subtotal, delivery

    def quote(self, rows, subtotal, delivery):
        breakup = []
        for requested, variant, product, inventory, total, maximum in rows:
            breakup.append({"@ondc/org/item_id": requested.id,
                "@ondc/org/item_quantity": {"count": requested.quantity.count}, "title": product.name,
                "@ondc/org/title_type": "item", "price": {"currency": "INR", "value": format(total, ".2f")},
                "item": {"quantity": {"available": {"count": str(inventory.quantity)},
                                       "maximum": {"count": str(maximum)}},
                         "price": {"currency": "INR", "value": format(variant.selling_price, ".2f")}}})
        breakup.append({"@ondc/org/item_id": rows[0][0].id, "title": "Delivery charges",
                        "@ondc/org/title_type": "delivery",
                        "price": {"currency": "INR", "value": format(delivery, ".2f")}})
        total = subtotal + delivery
        return {"price": {"value": format(total, ".2f"), "currency": "INR"}, "breakup": breakup, "ttl": "P1D"}

    def select(self, db, request):
        order = request.message.order
        seller, store, profile, rows, subtotal, delivery = self.resolve(db, order)
        quote = self.quote(rows, subtotal, delivery)
        selection = order.to_wire()
        checkout = db.scalar(select(CheckoutIntent).where(CheckoutIntent.transaction_id == request.context.transaction_id))
        if checkout is None:
            checkout = CheckoutIntent(transaction_id=request.context.transaction_id, bap_id=request.context.bap_id,
                provider_id=order.provider.id, store_id=store.id, selection=selection, quote=quote,
                expires_at=time.time() + 86400)
            db.add(checkout)
            db.flush()
        elif checkout.bap_id != request.context.bap_id:
            raise DiscoveryError("30000", "Transaction identity mismatch")
        elif checkout.state == "confirmed":
            raise DiscoveryError("30000", "Order transaction already confirmed")
        else:
            checkout.provider_id, checkout.store_id = order.provider.id, store.id
            checkout.selection, checkout.quote = selection, quote
            checkout.checkout, checkout.state = None, "selected"
            checkout.expires_at = time.time() + 86400
        fulfillment = {"id": profile.fulfillment_id, "type": "Delivery",
            "@ondc/org/provider_name": seller.name, "tracking": True,
            "@ondc/org/category": "Immediate Delivery", "@ondc/org/TAT": profile.stores[store.id].fulfillment_tat,
            "state": {"descriptor": {"code": "Serviceable"}}}
        items = [{"id": row[0].id, "fulfillment_id": profile.fulfillment_id} for row in rows]
        return {"context": callback_context(request.context, self.settings, "on_select"),
                "message": {"order": {"provider": order.provider.to_wire(), "items": items,
                "fulfillments": [fulfillment], "quote": quote}}}

    def init(self, db, request):
        order = request.message.order
        checkout = db.scalar(select(CheckoutIntent).where(CheckoutIntent.transaction_id == request.context.transaction_id))
        if checkout is None or checkout.expires_at <= time.time() or checkout.bap_id != request.context.bap_id:
            raise DiscoveryError("40003", "Quote unavailable")
        if self.cart(order) != self.stored_cart(checkout.selection):
            raise DiscoveryError("40003", "Selection does not match quoted cart")
        seller, store, profile, rows, subtotal, delivery = self.resolve(db, order)
        quote = self.quote(rows, subtotal, delivery)
        if quote["price"] != checkout.quote["price"]:
            raise DiscoveryError("40008", "Quote changed")
        checkout.checkout = order.to_wire()
        checkout.state = "initialized"
        checkout.expires_at = time.time() + 86400
        db.flush()
        payment = {"type": "ON-ORDER", "collected_by": "BAP"}
        response = order.to_wire()
        response["quote"] = quote
        response["payment"] = payment
        response["fulfillments"][0]["tracking"] = True
        return {"context": callback_context(request.context, self.settings, "on_init"), "message": {"order": response}}

    def confirm(self, db, request):
        incoming = request.message.order
        checkout = db.scalar(select(CheckoutIntent).where(
            CheckoutIntent.transaction_id == request.context.transaction_id).with_for_update())
        if checkout is None or checkout.checkout is None or checkout.expires_at <= time.time():
            raise DiscoveryError("40003", "Quote unavailable")
        if self.cart(incoming) != self.stored_cart(checkout.checkout):
            raise DiscoveryError("40003", "Confirmation does not match initialized cart")
        current = db.get(ONDCOrder, incoming.id)
        if current:
            if current.transaction_id != request.context.transaction_id:
                raise DiscoveryError("30000", "Order identifier conflict")
            return self.confirm_callback(request, current, incoming)
        seller, store, profile, rows, subtotal, delivery = self.resolve(db, incoming, lock=True)
        quote = self.quote(rows, subtotal, delivery)
        if incoming.quote.to_wire() != quote or money(incoming.payment.params.amount) != money(quote["price"]["value"]):
            raise DiscoveryError("40008", "Quote changed")
        now = time.time()
        fulfillment_snapshot = incoming.fulfillments[0].to_wire()
        fulfillment_snapshot["@ondc/org/TAT"] = profile.stores[store.id].fulfillment_tat
        order = ONDCOrder(id=incoming.id, transaction_id=request.context.transaction_id,
            checkout_id=checkout.id, bap_id=request.context.bap_id, state="Accepted",
            amount=money(quote["price"]["value"]), fulfillment=fulfillment_snapshot,
            payment=incoming.payment.to_wire(), billing=incoming.billing.to_wire(), created_at=now, updated_at=now)
        db.add(order)
        # Establish the parent before append-only audit/accounting rows. These
        # models intentionally have no ORM relationship that would otherwise
        # give SQLAlchemy a dependency edge for flush ordering.
        db.flush()
        db.add(OrderStateEvent(order_id=incoming.id, idempotency_key="confirm:" + request.context.transaction_id,
            from_state="created", to_state="accepted", fulfillment_state="Pending", actor=request.context.bap_id,
            source="protocol", occurred_at=now, detail={}))
        db.add(FinancialEvent(order_id=incoming.id, idempotency_key="expected-payment:" + request.context.transaction_id,
            event_type="expected_payment", status="expected", currency="INR", amount=order.amount,
            transaction_reference=None, occurred_at=now, detail={}))
        reference = incoming.payment.params.transaction_id
        if incoming.payment.status == "PAID":
            db.add(FinancialEvent(order_id=incoming.id, idempotency_key="recorded-payment:" + request.context.transaction_id,
                event_type="recorded_payment", status="recorded", currency="INR", amount=order.amount,
                transaction_reference=reference, occurred_at=now,
                detail={"trusted_source": request.context.bap_id, "not_bank_settlement_confirmation": True}))
        for requested, variant, product, inventory, total, maximum in rows:
            inventory.quantity -= requested.quantity.count
            db.add(ONDCOrderItem(order_id=incoming.id, item_id=requested.id, variant_id=variant.id,
                store_id=store.id, quantity=requested.quantity.count, unit_price=variant.selling_price,
                total_price=total))
        checkout.state = "confirmed"
        db.flush()
        return self.confirm_callback(request, order, incoming, quote, profile, store, seller)

    def confirm_callback(self, request, order, incoming, quote=None, profile=None, store=None, seller=None):
        payload = incoming.to_wire()
        payload["state"] = "Accepted"
        payload["quote"] = quote or incoming.quote.to_wire()
        payload["updated_at"] = stamp()
        if profile:
            fulfillment = payload["fulfillments"][0]
            fulfillment.update({"state": {"descriptor": {"code": "Pending"}}, "tracking": True,
                "@ondc/org/TAT": profile.stores[store.id].fulfillment_tat,
                "@ondc/org/provider_name": seller.name})
        return {"context": callback_context(request.context, self.settings, "on_confirm"),
                "message": {"order": payload}}

def validate_purchase_callback(payload):
    context = payload.get("context", {})
    action = context.get("action")
    if action not in {"on_select", "on_init", "on_confirm"} or not isinstance(payload.get("message", {}).get("order"), dict):
        raise ValueError("Invalid purchase callback")
    if action == "on_confirm" and payload["message"]["order"].get("state") != "Accepted":
        raise ValueError("Invalid confirmed order state")
    return payload
