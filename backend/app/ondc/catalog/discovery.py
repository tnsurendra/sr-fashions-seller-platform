
"""Read existing catalog plus persisted enrichment; prevalidate before ACK."""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models import Seller, Store, Product, Inventory, ProductVariant
from app.ondc.models import SellerPublication
from app.ondc.catalog.administration import load_profile, ProviderPublication
from app.ondc.protocol.errors import DiscoveryError
from decimal import Decimal
from app.ondc.catalog.mapper import map_catalog
from app.ondc.validators.discovery import validate_catalog_callback

def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

def build_callback(db, search, settings):
    enabled = db.scalars(select(SellerPublication).where(SellerPublication.enabled.is_(True))).all()
    if len(enabled) != 1:
        raise ValueError("Exactly one inventory seller provider must be enabled")
    publication = ProviderPublication.model_validate(enabled[0].data)
    seller = db.get(Seller, enabled[0].seller_id)
    profile = load_profile(db, seller.id)
    stores = db.scalars(select(Store).where(Store.seller_id == seller.id)).all()
    products = db.scalars(select(Product).where(Product.seller_id == seller.id)
                          .options(selectinload(Product.variants))).all()
    intent = search.message.intent
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
            if group.code not in {"bap_terms", "bap_features"}:
                raise ValueError("Unsupported discovery mode")
    if intent.category and intent.category.id:
        products = [p for p in products if profile.category_mapping.get(p.category) == intent.category.id]
    if intent.item and intent.item.descriptor and intent.item.descriptor.name:
        name = intent.item.descriptor.name.casefold()
        products = [p for p in products if name in p.name.casefold()]
    variant_ids = [v.id for p in products for v in p.variants]
    stock = db.scalars(select(Inventory).where(Inventory.variant_id.in_(variant_ids),
                      Inventory.store_id.in_([s.id for s in stores]))).all()
    stamp = utc_now()
    catalog = map_catalog(seller=seller, stores=stores, products=products, inventory=stock,
                         profile=profile, snapshot_at=stamp)
    context = search.context.to_wire()
    context.pop("key", None)
    context.update(action="on_search", timestamp=stamp, bpp_id=settings.subscriber_id,
                   bpp_uri=settings.subscriber_url, city=settings.city)
    callback = {"context": context, "message": {"catalog": catalog.to_wire()}}
    return validate_catalog_callback(callback).to_wire()
