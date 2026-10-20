from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database import Base
from app.models import Seller, Store, Product, ProductVariant, Inventory
from app.ondc.config import ONDCSettings, get_ondc_settings
from app.ondc.catalog.mapper import CatalogMappingError, map_catalog
from app.ondc.catalog.publication import PublicationProfile
from app.ondc.catalog.taxonomy import category_definition, validate_attributes
from app.ondc.protocol.responses import ProtocolError, ProtocolResponse, ack, nack
from app.ondc.protocol.specification import validate_official
from app.ondc.schemas.context import Context
from app.ondc.schemas.catalog import Catalog
from app.ondc.validators.discovery import validate_search, validate_catalog_callback, validation_nack, require_fresh_context

SNAPSHOT = "2026-10-07T12:00:00.000Z"


@pytest.fixture
def context():
    return {"domain": "ONDC:RET12", "country": "IND", "city": "std:080", "action": "search",
            "core_version": "1.2.5", "bap_id": "buyer.example.com", "bap_uri": "https://buyer.example.com/ondc",
            "transaction_id": "T1", "message_id": "M1", "timestamp": SNAPSHOT, "ttl": "PT30S"}


@pytest.fixture
def settings_values():
    return {"subscriber_id": "seller.example.com", "subscriber_url": "https://seller.example.com/ondc",
            "callback_url": "https://seller.example.com/ondc", "unique_key_id": "key-1", "city": "std:080"}


def test_config_env_and_private_key(monkeypatch, settings_values):
    for name, value in settings_values.items():
        monkeypatch.setenv("ONDC_" + name.upper(), value)
    monkeypatch.setenv("ONDC_SIGNING_PRIVATE_KEY", "PRIVATE-TEST-KEY")
    settings = ONDCSettings(_env_file=None)
    assert settings.domain == "ONDC:RET12" and settings.node_type == "ISN"
    assert settings.protocol_version == "1.2.5"
    assert settings.signing_private_key.get_secret_value() == "PRIVATE-TEST-KEY"
    assert "PRIVATE-TEST-KEY" not in repr(settings)
    assert "signing_private_key" not in settings.model_dump()
    get_ondc_settings.cache_clear()


@pytest.mark.parametrize("field,value", [("domain", "ONDC:RET10"), ("protocol_version", "1.2.0"),
    ("city", "Bengaluru"), ("node_type", "MSN"), ("subscriber_id", ""),
    ("subscriber_url", "https://other.example.com/ondc"), ("callback_url", "ftp://seller.example.com")])
def test_invalid_configuration(settings_values, field, value):
    settings_values[field] = value
    with pytest.raises(ValidationError):
        ONDCSettings(_env_file=None, **settings_values)


def test_nonlocal_https(settings_values):
    settings_values["subscriber_url"] = "http://seller.example.com/ondc"
    with pytest.raises(ValidationError):
        ONDCSettings(_env_file=None, environment="production", **settings_values)


def test_config_missing_values_fail_closed(monkeypatch):
    for name in ["SUBSCRIBER_ID", "SUBSCRIBER_URL", "CALLBACK_URL", "UNIQUE_KEY_ID", "CITY"]:
        monkeypatch.delenv("ONDC_" + name, raising=False)
    with pytest.raises(ValidationError):
        ONDCSettings(_env_file=None)


def test_context_valid_official_strings(context):
    assert Context.model_validate(context).transaction_id == "T1"
    validate_official(context, "Context", reconcile=False)
    context["city"] = "*"
    assert Context.model_validate(context).city == "*"


@pytest.mark.parametrize("field,value", [("domain", "ONDC:RET10"), ("action", "confirm"),
    ("core_version", "2.0.2"), ("country", "IN"), ("city", "Bengaluru"),
    ("timestamp", "2026-10-07T12:00:00"), ("timestamp", "2026-02-30T12:00:00Z"),
    ("ttl", "PT31S"), ("ttl", "P1D"), ("ttl", "PT0S"), ("ttl", "30"),
    ("message_id", ""), ("transaction_id", 1), ("bap_uri", "https://wrong.example.com/ondc"),
    ("bap_uri", "https://user:secret@buyer.example.com/ondc")])
def test_invalid_context(context, field, value):
    context[field] = value
    with pytest.raises(ValidationError):
        Context.model_validate(context)


@pytest.mark.parametrize("field", ["domain", "country", "city", "action", "core_version", "bap_id", "bap_uri", "transaction_id", "message_id", "timestamp"])
def test_required_context_fields(context, field):
    del context[field]
    with pytest.raises(ValidationError):
        Context.model_validate(context)


def test_context_unknown_fields(context):
    context["private_key"] = "secret"
    with pytest.raises(ValidationError):
        Context.model_validate(context)


def test_on_search_identity_and_freshness(context):
    context["action"] = "on_search"
    with pytest.raises(ValidationError):
        Context.model_validate(context)
    context.update(bpp_id="seller.example.com", bpp_uri="https://seller.example.com/ondc")
    assert Context.model_validate(context).bpp_id == "seller.example.com"
    context["action"] = "search"
    ctx = Context.model_validate(context)
    require_fresh_context(ctx, now=datetime(2026, 10, 7, 12, 0, 29, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="expired"):
        require_fresh_context(ctx, now=datetime(2026, 10, 7, 12, 0, 30, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="future"):
        require_fresh_context(ctx, now=datetime(2026, 10, 7, 11, 59, tzinfo=timezone.utc))


def test_first_search_contract(context):
    request = {"context": context, "message": {"intent": {
        "category": {"id": "Shirts"}, "fulfillment": {"type": "Delivery"},
        "payment": {"@ondc/org/buyer_app_finder_fee_type": "percent", "@ondc/org/buyer_app_finder_fee_amount": "3.54"},
        "tags": [{"code": "bap_features", "list": [{"code": "003", "value": "yes"}]}],
    }}}
    assert validate_search(request).message.intent.category.id == "Shirts"
    request["message"]["intent"]["payment"]["@ondc/org/buyer_app_finder_fee_type"] = "Percent"
    with pytest.raises(ValidationError):
        validate_search(request)


@pytest.fixture
def fashion_catalog():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False, autoflush=False) as session:
        seller = Seller(name="SR Fashions", email="sales@sr-fashions.example.com")
        session.add(seller)
        session.flush()
        stores = [Store(seller_id=seller.id, name="SR Fashions Flagship Store", address="Bengaluru store"),
                  Store(seller_id=seller.id, name="SR Fashions City Store", address="Second Bengaluru store")]
        session.add_all(stores)
        session.flush()
        products = []
        specs = [("SR Essentials Cotton Shirt", "SR Essentials", "Shirts", [("SR-SHIRT-BLUE-M", "M", "Blue", 20), ("SR-SHIRT-BLUE-L", "L", "Blue", 12), ("SR-SHIRT-WHITE-M", "M", "White", 0)]),
                 ("SR Denim Straight-Fit Jeans", "SR Denim", "Jeans", [("SR-JEANS-INDIGO-32", "32", "Indigo", 15)]),
                 ("SR Studio Printed Cotton Kurta", "SR Studio", "Kurtas", [("SR-KURTA-GREEN-M", "M", "Green", 8)]),
                 ("SR Essentials Crew-Neck T-Shirt", "SR Essentials", "T-Shirts", [("SR-TEE-BLACK-M", "M", "Black", 30)]),
                 ("SR Active Zip-Up Hoodie", "SR Active", "Hoodies", [("SR-HOODIE-GREY-L", "L", "Grey", 0)])]
        inventory = []
        for name, brand, category, variants in specs:
            product = Product(seller_id=seller.id, name=name, brand=brand, category=category, description="Professionally tailored garment")
            session.add(product)
            session.flush()
            for sku, size, color, stock in variants:
                variant = ProductVariant(product=product, sku=sku, size=size, color=color, mrp=Decimal("1499.00"), selling_price=Decimal("1199.00"))
                session.add(variant)
                session.flush()
                inventory.append(Inventory(variant_id=variant.id, store_id=stores[0].id, quantity=stock))
            products.append(product)
        inventory.append(Inventory(variant_id=products[0].variants[0].id, store_id=stores[1].id, quantity=3))
        session.add_all(inventory)
        session.commit()
        image = "https://seller.example.com/images/catalog.png"
        descriptor = {"name": "SR Fashions", "symbol": image, "short_desc": "Fashion retail", "long_desc": "SR Fashions clothing collections", "images": [image]}
        bpp = {**descriptor, "tags": [{"code": "bpp_terms", "list": [{"code": "np_type", "value": "ISN"}, {"code": "accept_bap_terms", "value": "Y"}]}]}
        store_metadata = {}
        for store in stores:
            lid = f"store-{store.id}"
            store_metadata[store.id] = {"gps": "12.9675,77.7496", "address": {"locality": "Jayanagar", "street": "4th Block", "city": "Bengaluru", "state": "KA", "area_code": "560076"},
                "hours": {"start": "1000", "end": "2000"}, "tags": [
                    {"code": "timing", "list": [{"code": "location", "value": lid}, {"code": "type", "value": "All"}, {"code": "day_from", "value": "1"}, {"code": "day_to", "value": "7"}, {"code": "time_from", "value": "1000"}, {"code": "time_to", "value": "2000"}]},
                    {"code": "serviceability", "list": [{"code": "location", "value": lid}, {"code": "category", "value": "Shirts"}, {"code": "type", "value": "12"}, {"code": "val", "value": "IND"}, {"code": "unit", "value": "country"}]}]}
            for category in ["Jeans", "Kurtas & Kurta Sets", "T Shirts", "Sweatshirts"]:
                group = deepcopy(store_metadata[store.id]["tags"][1])
                next(tag for tag in group["list"] if tag["code"] == "category")["value"] = category
                store_metadata[store.id]["tags"].append(group)
        product_metadata = {}
        for product in products:
            product_metadata[product.id] = {"images": [image], "attributes": {"gender": "male", "fabric": "cotton", "size_chart": "https://seller.example.com/images/size-chart.png"},
                "colour_hex_by_name": {"Blue": "#0000FF", "White": "#FFFFFF", "Indigo": "#4B0082", "Green": "#008000", "Black": "#000000", "Grey": "#808080"},
                "origin_country": "IND", "statutory": {"manufacturer_or_packer_name": "SR Apparel", "manufacturer_or_packer_address": "Bengaluru", "common_or_generic_name_of_commodity": "Garment", "month_year_of_manufacture_packing_import": "10/2026"},
                "returnable": True, "cancellable": True, "return_window": "P7D", "seller_pickup_return": True, "time_to_ship": "P1D", "available_on_cod": False,
                "consumer_care": "SR Customer Care,support@sr-fashions.example.com,18000000000", "maximum_per_order": 5}
        profile = PublicationProfile.model_validate({"bpp_descriptor": bpp, "provider_descriptor": descriptor, "provider_ttl": "P1D", "fulfillment_id": "F1", "fulfillment_type": "Delivery", "contact": {"phone": "18000000000", "email": "support@sr-fashions.example.com"},
            "category_mapping": {"Shirts": "Shirts", "Jeans": "Jeans", "Kurtas": "Kurtas & Kurta Sets", "T-Shirts": "T Shirts", "Hoodies": "Sweatshirts"}, "stores": store_metadata, "products": product_metadata})
        yield {"seller": seller, "stores": stores, "products": products, "inventory": inventory, "profile": profile, "snapshot_at": SNAPSHOT}
    engine.dispose()


def test_ret12_mapper_multiple_skus_sizes_colours_inventory(fashion_catalog):
    before = [(row.id, row.quantity) for row in fashion_catalog["inventory"]]
    catalog = map_catalog(**fashion_catalog)
    provider = catalog.providers[0]
    assert provider.descriptor.name == "SR Fashions"
    assert len(provider.items) == 8 and len(provider.locations) == 2
    assert len({item.id for item in provider.items}) == 8
    items = {item.id: item.to_wire() for item in provider.items}
    first_store = fashion_catalog["stores"][0].id
    blue = items[f"SR-SHIRT-BLUE-M@store-{first_store}"]
    assert blue["quantity"]["available"]["count"] == "20"
    assert blue["price"] == {"currency": "INR", "value": "1199.00", "maximum_value": "1499.00"}
    assert blue["descriptor"]["images"]
    assert blue["category_id"] == "Shirts"
    attrs = {tag["code"]: tag["value"] for group in blue["tags"] if group["code"] == "attribute" for tag in group["list"]}
    assert attrs["size"] == "M" and attrs["colour"] == "#0000FF" and attrs["colour_name"] == "Blue"
    assert attrs["brand"] == "SR Essentials"
    assert items[f"SR-SHIRT-WHITE-M@store-{first_store}"]["quantity"]["available"]["count"] == "0"
    assert [(row.id, row.quantity) for row in fashion_catalog["inventory"]] == before
    assert {item.category_id for item in provider.items} == {"Shirts", "Jeans", "Kurtas & Kurta Sets", "T Shirts", "Sweatshirts"}
    for item in provider.items:
        assert item.parent_item_id in {group.id for group in provider.categories}
    assert Catalog.model_validate(catalog.to_wire()).to_wire() == catalog.to_wire()


def test_catalog_callback_official_contract(fashion_catalog, context):
    context.update(action="on_search", bpp_id="seller.example.com", bpp_uri="https://seller.example.com/ondc")
    payload = {"context": context, "message": {"catalog": map_catalog(**fashion_catalog).to_wire()}}
    assert validate_catalog_callback(payload).message.catalog.providers
    payload["context"]["timestamp"] = "2026-10-07T11:59:59Z"
    with pytest.raises(ValidationError, match="exceeds"):
        validate_catalog_callback(payload)


def test_authoritative_fashion_example_and_schema_discrepancies():
    from jsonschema import ValidationError as SchemaError
    payload = json.loads((Path(__file__).parent / "fixtures/official-ret12-on-search.json").read_text())
    validate_official(payload, "on_search")
    # Generated schema disagrees with its own current API contract: retain evidence.
    with pytest.raises(SchemaError):
        validate_official(payload, "on_search", reconcile=False)


@pytest.mark.parametrize("gap", ["images", "attributes", "colour", "category", "store", "product", "ownership", "duplicate_stock", "negative_stock", "missing_timing"])
def test_catalog_missing_or_invalid_publication_data(fashion_catalog, gap):
    profile = fashion_catalog["profile"]
    pid = fashion_catalog["products"][0].id
    sid = fashion_catalog["stores"][0].id
    if gap == "images":
        profile.products[pid].images.clear()
    elif gap == "attributes":
        profile.products[pid].attributes.pop("fabric")
    elif gap == "colour":
        profile.products[pid].colour_hex_by_name.pop("Blue")
    elif gap == "category":
        profile.category_mapping["Shirts"] = "Made-up category"
    elif gap == "store":
        del profile.stores[sid]
    elif gap == "product":
        del profile.products[pid]
    elif gap == "ownership":
        fashion_catalog["stores"][0].seller_id = 999
    elif gap == "duplicate_stock":
        fashion_catalog["inventory"].append(fashion_catalog["inventory"][0])
    elif gap == "negative_stock":
        fashion_catalog["inventory"][0].quantity = -1
    elif gap == "missing_timing":
        profile.stores[sid].tags = [group for group in profile.stores[sid].tags if group.code != "timing"]
    with pytest.raises((ValueError, ValidationError, IndexError)):
        map_catalog(**fashion_catalog)


def test_missing_inventory_not_advertised(fashion_catalog):
    fashion_catalog["inventory"] = [row for row in fashion_catalog["inventory"] if row.variant_id != fashion_catalog["products"][0].variants[0].id]
    assert not any(item.id.startswith("SR-SHIRT-BLUE-M@") for item in map_catalog(**fashion_catalog).providers[0].items)


def test_unmapped_category_does_not_fallback(fashion_catalog):
    del fashion_catalog["profile"].category_mapping["Kurtas"]
    with pytest.raises(CatalogMappingError, match="Unmapped"):
        map_catalog(**fashion_catalog)


def test_suggestive_enum_does_not_reject_real_sizes(fashion_catalog):
    fashion_catalog["products"][0].variants[0].size = "Custom 41"
    fashion_catalog["profile"].products[fashion_catalog["products"][0].id].colour_hex_by_name["Blue"] = None
    item = map_catalog(**fashion_catalog).providers[0].items[0]
    attrs = {tag.code: tag.value for group in item.tags if group.code == "attribute" for tag in group.list}
    assert attrs["size"] == "Custom 41" and "colour" not in attrs


@pytest.mark.parametrize("category", ["T-Shirts", "Kurtas", "Hoodies", "Arbitrary"])
def test_unknown_official_taxonomy_rejected(category):
    with pytest.raises(ValueError):
        category_definition(category)


def test_ack_nack_official_wire_schema():
    assert ack() == {"message": {"ack": {"status": "ACK"}}}
    validate_official(ack(), "search_response", reconcile=False)
    rejected = nack(ProtocolError(type="JSON-SCHEMA-ERROR", code="30000", path="/context/domain", message="Invalid protocol request"))
    assert rejected["message"]["ack"]["status"] == "NACK"
    validate_official(rejected, "search_response", reconcile=False)
    with pytest.raises(ValidationError):
        ProtocolError(type="DOMAIN-ERROR", code="99999")
    with pytest.raises(ValidationError):
        ProtocolResponse.model_validate({"message": {"ack": {"status": "NACK"}}})
    with pytest.raises(ValidationError):
        ProtocolResponse.model_validate({"message": {"ack": {"status": "ACK"}}, "error": rejected["error"]})


def test_invalid_context_nack_does_not_expose_input(context):
    context["domain"] = "PRIVATE-INPUT"
    with pytest.raises(ValidationError) as caught:
        validate_search({"context": context, "message": {"intent": {}}})
    response = validation_nack(caught.value)
    assert response["error"]["type"] == "CONTEXT-ERROR"
    assert response["error"]["path"] == "/context/domain"
    assert "PRIVATE-INPUT" not in json.dumps(response)


def test_admin_app_remains_isolated(client, monkeypatch):
    monkeypatch.setenv("ONDC_DOMAIN", "invalid")
    assert client.get("/").json()["name"] == "SR Fashions"
    assert client.get("/health").status_code == 200
    for path in ["/select", "/init", "/confirm", "/status", "/cancel", "/update", "/on_search"]:
        assert client.post(path, json={}).status_code == 404
    assert client.post("/search", json={}).json()["message"]["ack"]["status"] == "NACK"
    assert "ONDC_SIGNING_PRIVATE_KEY" not in client.get("/openapi.json").text


def test_missing_category_serviceability_rejected(fashion_catalog):
    profile = fashion_catalog["profile"]
    sid = fashion_catalog["stores"][0].id
    profile.stores[sid].tags = [group for group in profile.stores[sid].tags
                               if group.code != "serviceability" or not any(tag.code == "category" and tag.value == "Jeans" for tag in group.list)]
    with pytest.raises(CatalogMappingError, match="serviceability"):
        map_catalog(**fashion_catalog)


@pytest.mark.parametrize("field,value", [("gps", "91.0000,77.0000"), ("gps", "12.9,77.7")])
def test_invalid_gps(fashion_catalog, field, value):
    fashion_catalog["profile"].stores[fashion_catalog["stores"][0].id].gps = value
    with pytest.raises(ValidationError):
        map_catalog(**fashion_catalog)


def test_invalid_price_and_return_policy(fashion_catalog):
    meta = fashion_catalog["profile"].products[fashion_catalog["products"][0].id]
    meta.return_window = None
    with pytest.raises(ValidationError, match="return_window"):
        map_catalog(**fashion_catalog)
    meta.return_window = "P7D"
    fashion_catalog["products"][0].variants[0].selling_price = Decimal("1500.00")
    with pytest.raises(ValidationError, match="exceeds MRP"):
        map_catalog(**fashion_catalog)


def test_unknown_wire_field_and_reference_rejected(fashion_catalog):
    payload = map_catalog(**fashion_catalog).to_wire()
    item = payload["bpp/providers"][0]["items"][0]
    item["sku"] = "invented-wire-field"
    with pytest.raises(ValidationError):
        Catalog.model_validate(payload)
    del item["sku"]
    item["location_id"] = "missing-store"
    with pytest.raises(ValidationError, match="references"):
        Catalog.model_validate(payload)


def test_invalid_stock_wire_type(fashion_catalog):
    payload = map_catalog(**fashion_catalog).to_wire()
    payload["bpp/providers"][0]["items"][0]["quantity"]["available"]["count"] = 20
    with pytest.raises(ValidationError):
        Catalog.model_validate(payload)


def test_json_schema_nack(context):
    with pytest.raises(ValidationError) as caught:
        validate_search({"context": context, "message": {"intent": {"fabricated": "PRIVATE-INPUT"}}})
    response = validation_nack(caught.value)
    assert response["error"]["type"] == "JSON-SCHEMA-ERROR"
    assert "PRIVATE-INPUT" not in json.dumps(response)


def test_empty_snapshot_fails_closed(fashion_catalog):
    fashion_catalog["inventory"] = []
    with pytest.raises(CatalogMappingError, match="No inventory-backed"):
        map_catalog(**fashion_catalog)


def test_official_schema_format_and_error_sanitization(context):
    from jsonschema import ValidationError as SchemaError
    context["timestamp"] = "PRIVATE-INPUT"
    with pytest.raises(SchemaError) as caught:
        validate_official(context, "Context", reconcile=False)
    # Context alone has a timestamp path, so generic schema error is appropriate.
    response = validation_nack(caught.value)
    assert response["error"]["path"] == "/timestamp"
    assert "PRIVATE-INPUT" not in json.dumps(response)


def test_invalid_discovery_category_rejected(context):
    with pytest.raises(ValidationError):
        validate_search({"context": context, "message": {"intent": {"category": {"id": "T-Shirts"}}}})
