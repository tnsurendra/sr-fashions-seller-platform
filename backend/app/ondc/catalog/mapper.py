"""Pure mapping of existing ORM objects. No session writes, I/O or network calls."""
from collections.abc import Sequence
from decimal import Decimal
from app.models import Inventory, Product, Seller, Store
from app.ondc.catalog.publication import PublicationProfile
from app.ondc.catalog.taxonomy import category_definition, validate_attributes
from app.ondc.schemas.catalog import Catalog
from app.ondc.utils.validation import timestamp


class CatalogMappingError(ValueError):
    """Missing or inconsistent publication data: never fall back to invented data."""


def _tag(code, values):
    return {"code": code, "list": [{"code": key, "value": value} for key, value in values]}


def map_catalog(*, seller: Seller, stores: Sequence[Store], products: Sequence[Product],
                inventory: Sequence[Inventory], profile: PublicationProfile, snapshot_at: str) -> Catalog:
    profile = PublicationProfile.model_validate(profile.model_dump())
    timestamp(snapshot_at)
    if not stores or not products:
        raise CatalogMappingError("A full catalog requires stores and products")
    store_map = {store.id: store for store in stores}
    if len(store_map) != len(stores) or any(store.seller_id != seller.id for store in stores):
        raise CatalogMappingError("Duplicate store or store ownership mismatch")
    if len({product.id for product in products}) != len(products) or any(product.seller_id != seller.id for product in products):
        raise CatalogMappingError("Duplicate product or product ownership mismatch")
    variants = {variant.id: variant for product in products for variant in product.variants}
    skus = [variant.sku for product in products for variant in product.variants]
    if len(variants) != len(skus) or len(set(skus)) != len(skus):
        raise CatalogMappingError("Duplicate variant or SKU")
    stocks = {}
    for row in inventory:
        key = (row.variant_id, row.store_id)
        if row.store_id not in store_map or row.variant_id not in variants:
            raise CatalogMappingError("Inventory references a store/variant outside this seller snapshot")
        if key in stocks or isinstance(row.quantity, bool) or not isinstance(row.quantity, int) or row.quantity < 0:
            raise CatalogMappingError("Duplicate inventory pair or invalid stock")
        stocks[key] = row.quantity
    event = {"label": "enable", "timestamp": snapshot_at}
    locations, tags, groups, items = [], [], [], []
    for store in sorted(stores, key=lambda row: row.id):
        meta = profile.stores.get(store.id)
        if meta is None:
            raise CatalogMappingError(f"Missing publication metadata for store {store.id}")
        location_id = f"store-{store.id}"
        locations.append({"id": location_id, "descriptor": {"name": store.name}, "gps": meta.gps,
                          "address": meta.address.to_wire(), "time": {**event, "range": meta.hours.to_wire()}})
        location_tags = meta.tags
        for required in ["timing", "serviceability"]:
            matching = [group for group in location_tags if group.code == required]
            if not matching or any({tag.code: tag.value for tag in group.list}.get("location") != location_id for group in matching):
                raise CatalogMappingError(f"Missing or invalid {required} location tags for store {store.id}")
        tags.extend(group.to_wire() for group in location_tags)
    for product in sorted(products, key=lambda row: row.id):
        category = profile.category_mapping.get(product.category)
        if category is None:
            raise CatalogMappingError(f"Unmapped internal category: {product.category}")
        category_definition(category)
        meta = profile.products.get(product.id)
        if meta is None:
            raise CatalogMappingError(f"Missing publication metadata for product {product.id}")
        if not product.variants:
            raise CatalogMappingError(f"Product {product.id} has no variants")
        for store in sorted(stores, key=lambda row: row.id):
            listed = [variant for variant in sorted(product.variants, key=lambda row: row.id) if (variant.id, store.id) in stocks]
            # Missing stock rows mean not stocked here, not an invented zero-stock listing.
            if not listed:
                continue
            group_id = f"product-{product.id}-store-{store.id}"
            groups.append({"id": group_id, "descriptor": {"name": product.name}, "tags": [
                _tag("type", [("type", "variant_group")]),
                _tag("attr", [("name", "item.tags.attribute.colour"), ("seq", "1")]),
                _tag("attr", [("name", "item.tags.attribute.size"), ("seq", "2")]),
            ]})
            for variant in listed:
                if variant.product_id != product.id:
                    raise CatalogMappingError("Variant ownership mismatch")
                if variant.color not in meta.colour_hex_by_name:
                    raise CatalogMappingError(f"Colour mapping missing for {variant.color}")
                attributes = dict(meta.attributes)
                # Source-of-truth fields always come from existing retailer models.
                attributes.update(size=variant.size, colour_name=variant.color, brand=product.brand)
                colour = meta.colour_hex_by_name[variant.color]
                attributes.pop("colour", None)
                if colour is not None:
                    attributes["colour"] = colour
                validate_attributes(category, attributes)
                if not isinstance(variant.mrp, Decimal) or not isinstance(variant.selling_price, Decimal):
                    raise CatalogMappingError("Prices must be Decimal values from the database")
                description = product.description or product.name
                items.append({"id": f"{variant.sku}@store-{store.id}", "parent_item_id": group_id, "time": event,
                    "descriptor": {"name": product.name, "symbol": meta.images[0], "images": meta.images,
                                   "short_desc": product.name, "long_desc": description},
                    "quantity": {"unitized": {"measure": {"unit": "unit", "value": "1"}},
                                 "available": {"count": str(stocks[(variant.id, store.id)])},
                                 "maximum": {"count": str(meta.maximum_per_order)}},
                    "price": {"currency": "INR", "value": format(variant.selling_price, ".2f"), "maximum_value": format(variant.mrp, ".2f")},
                    "category_id": category, "location_id": f"store-{store.id}", "fulfillment_id": profile.fulfillment_id,
                    "@ondc/org/returnable": meta.returnable, "@ondc/org/cancellable": meta.cancellable,
                    "@ondc/org/return_window": meta.return_window, "@ondc/org/seller_pickup_return": meta.seller_pickup_return,
                    "@ondc/org/time_to_ship": meta.time_to_ship, "@ondc/org/available_on_cod": meta.available_on_cod,
                    "@ondc/org/contact_details_consumer_care": meta.consumer_care,
                    "@ondc/org/statutory_reqs_packaged_commodities": meta.statutory.to_wire(),
                    "tags": [_tag("origin", [("country", meta.origin_country)]), _tag("attribute", sorted(attributes.items()))]})
    serviceable = {(tag["value"], next(entry["value"] for entry in group["list"] if entry["code"] == "category"))
                   for group in tags if group["code"] == "serviceability"
                   for tag in group["list"] if tag["code"] == "location"}
    for item in items:
        if (item["location_id"], item["category_id"]) not in serviceable:
            raise CatalogMappingError("Missing serviceability for published location/category")
    if not items:
        raise CatalogMappingError("No inventory-backed items available for publication")
    provider_descriptor = profile.provider_descriptor.to_wire()
    provider_descriptor["name"] = seller.name
    payload = {"bpp/descriptor": profile.bpp_descriptor.to_wire(), "bpp/providers": [{
        "id": f"seller-{seller.id}", "time": event, "descriptor": provider_descriptor, "ttl": profile.provider_ttl,
        "fulfillments": [{"id": profile.fulfillment_id, "type": profile.fulfillment_type, "contact": profile.contact.to_wire()}],
        "locations": locations, "categories": groups, "items": items, "tags": tags,
    }]}
    return Catalog.model_validate(payload)
