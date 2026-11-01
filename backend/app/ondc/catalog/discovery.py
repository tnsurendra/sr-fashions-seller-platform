
"""Read existing catalog plus persisted enrichment; prevalidate before ACK."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models import Seller, Store, Product, Inventory, ProductVariant
from app.ondc.models import SellerPublication, CatalogPublicationState, CatalogSubscription
import time
from app.ondc.catalog.administration import load_profile, ProviderPublication
from app.ondc.protocol.errors import DiscoveryError
from decimal import Decimal
from app.ondc.catalog.mapper import map_catalog
from app.ondc.validators.discovery import validate_catalog_callback

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def _instant(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Incremental timestamps require timezone")
    return parsed

def _changed(value, start, end):
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return start <= value <= end

def incremental_window(intent):
    groups = [group for group in (intent.tags or []) if group.code == "catalog_inc"]
    if not groups:
        return None
    if len(groups) != 1:
        raise ValueError("Duplicate catalog_inc tag")
    values = {tag.code: tag.value for tag in groups[0].list}
    if "mode" in values:
        if values["mode"] not in {"start", "stop"} or set(values) - {"mode", "start_time"}:
            raise ValueError("Invalid continuous incremental request")
        return values
    if set(values) != {"start_time", "end_time"}:
        raise ValueError("Incremental pull requires start_time and end_time")
    start, end = _instant(values["start_time"]), _instant(values["end_time"])
    if start > end or (end - start).total_seconds() > 86400:
        raise ValueError("Invalid incremental refresh window")
    return start, end

def build_callback(db, search, settings):
    enabled = db.scalars(select(SellerPublication).where(SellerPublication.enabled.is_(True))).all()
    if len(enabled) != 1:
        raise ValueError("Exactly one inventory seller provider must be enabled")
    publication = ProviderPublication.model_validate(enabled[0].data)
    seller = db.get(Seller, enabled[0].seller_id)
    profile = load_profile(db, seller.id)
    stores = db.scalars(select(Store).where(Store.seller_id == seller.id)).all()
    stores = [store for store in stores if profile.stores[store.id].enabled]
    products = db.scalars(select(Product).where(Product.seller_id == seller.id)
                          .options(selectinload(Product.variants))).all()
    intent = search.message.intent
    window = incremental_window(intent)
    if isinstance(window, dict):
        subscription = db.scalar(select(CatalogSubscription).where(
            CatalogSubscription.bap_id == search.context.bap_id,
            CatalogSubscription.transaction_id == search.context.transaction_id))
        now = time.time()
        if window["mode"] == "stop":
            if subscription is not None:
                subscription.status, subscription.updated_at = "stopped", now
            return None, {}, True
        cursor = _instant(window.get("start_time", search.context.timestamp)).timestamp()
        if subscription is None:
            subscription = CatalogSubscription(bap_id=search.context.bap_id, bap_uri=search.context.bap_uri,
                transaction_id=search.context.transaction_id, status="active",
                interval_seconds=settings.catalog_sync_interval_seconds, cursor_at=cursor,
                next_run_at=now + settings.catalog_sync_interval_seconds, created_at=now, updated_at=now)
            db.add(subscription)
        else:
            subscription.status, subscription.cursor_at = "active", cursor
            subscription.bap_uri, subscription.updated_at = search.context.bap_uri, now
            subscription.next_run_at = now + subscription.interval_seconds
        return None, {}, True
    if intent.payment:
        policy = publication.finder_fee_policy
        fee = intent.payment
        if (policy is None or fee.finder_fee_type != policy.finder_fee_type or fee.finder_fee_amount is None or
            not Decimal(policy.finder_fee_amount_min) <= Decimal(fee.finder_fee_amount) <= Decimal(policy.finder_fee_amount_max)):
            raise DiscoveryError("41001", "Finder fee not acceptable")
    if intent.tags and any(group.code == "bap_terms" for group in intent.tags):
        accepted = [tag.value for group in (profile.bpp_descriptor.tags or []) if group.code == "bpp_terms"
                    for tag in group.list if tag.code == "accept_bap_terms"]
        if accepted != ["Y"]:
            raise DiscoveryError("50005", "Terms and Conditions unacceptable")
    if intent.fulfillment and intent.fulfillment.type and intent.fulfillment.type != profile.fulfillment_type:
        raise ValueError("Unsupported fulfillment")
    if intent.fulfillment and intent.fulfillment.end:
        raise ValueError("Location filtered discovery is not yet supported")
    if intent.tags:
        for group in intent.tags:
            if group.code not in {"bap_terms", "bap_features", "catalog_inc"}:
                raise ValueError("Unsupported discovery mode")
    if intent.category and intent.category.id:
        products = [p for p in products if profile.category_mapping.get(p.category) == intent.category.id]
    if intent.item and intent.item.descriptor and intent.item.descriptor.name:
        name = intent.item.descriptor.name.casefold()
        products = [p for p in products if name in p.name.casefold()]
    variant_ids = [v.id for p in products for v in p.variants]
    stock = db.scalars(select(Inventory).where(Inventory.variant_id.in_(variant_ids),
                      Inventory.store_id.in_([s.id for s in stores]))).all()
    if window:
        start, end = window
        changed_states = db.scalars(select(CatalogPublicationState).where(
            CatalogPublicationState.changed_at >= start.timestamp(),
            CatalogPublicationState.changed_at <= end.timestamp())).all()
        full = any(row.entity_type in {"provider", "store"} for row in changed_states)
        changed_products = {row.entity_id for row in changed_states if row.entity_type == "product"}
        if not full:
            changed_variant_ids = {variant.id for product in products for variant in product.variants
                                   if product.id in changed_products or _changed(product.updated_at, start, end)
                                   or _changed(variant.updated_at, start, end)}
            stock = [row for row in stock if row.variant_id in changed_variant_ids or _changed(row.updated_at, start, end)]
            stocked = {row.variant_id for row in stock}
            products = [product for product in products if any(v.id in stocked for v in product.variants)]
            if not stock:
                return None, {"X-ONDC-Search-Response": "inc"}, True
    stamp = utc_now()
    catalog = map_catalog(seller=seller, stores=stores, products=products, inventory=stock,
                         profile=profile, snapshot_at=stamp)
    context = search.context.to_wire()
    context.pop("key", None)
    context.update(action="on_search", timestamp=stamp, bpp_id=settings.subscriber_id,
                   bpp_uri=settings.subscriber_url, city=settings.city)
    callback = {"context": context, "message": {"catalog": catalog.to_wire()}}
    return validate_catalog_callback(callback).to_wire(), ({"X-ONDC-Search-Response": "inc"} if window else {}), False
