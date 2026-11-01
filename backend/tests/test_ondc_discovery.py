
import asyncio
import base64
import gzip
import hashlib
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import create_engine, select, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
from app.models import Seller, Store, Product, ProductVariant, Inventory
from app.ondc.models import (SellerPublication, StorePublicationRow, ProductPublicationRow, DiscoveryMessage,
                             CatalogPublicationState, ONDCOrder, FinancialEvent, ReturnRequest,
                             CatalogSubscription, CatalogPublicationJob)
from app.ondc.config import ONDCSettings
from app.ondc.signing.crypto import generate_keys, sign, parse, verify, digest, signing_string, SignatureError, private_key
from app.ondc.clients.http import SignedClient, CallbackError, serialize
from app.ondc.registry.client import RegistryClient, SubscriberNotFound, RegistryError
from app.ondc.protocol.service import DiscoveryService
from app.ondc.protocol.purchase import PurchaseService
from app.ondc.protocol.post_order import PostOrderService
from app.ondc.protocol.replay import cleanup
from app.ondc.catalog.discovery import build_callback
from app.ondc.validators.discovery import validate_search
from mock_buyer import MockBuyer

@pytest.fixture
def discovery():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def enable_fk(conn, record):
        conn.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    seller_private, seller_public = generate_keys()
    buyer_private, buyer_public = generate_keys()
    gateway_private, gateway_public = generate_keys()
    settings = ONDCSettings(_env_file=None, subscriber_id="seller.example.com",
        subscriber_url="https://seller.example.com", callback_url="https://seller.example.com",
        unique_key_id="seller-key", city="std:080", registry_url="https://registry.example.com/v2.0/lookup",
        signing_private_key=SecretStr(seller_private), allow_local_peer_search=True, allow_local_callbacks=True)
    buyer = MockBuyer(buyer_private, seller_public)
    records = {
        "buyer.example.com": (buyer_public, "buyer-key", "BAP", "https://buyer.example.com/ondc"),
        "gateway.example.com": (gateway_public, "gateway-key", "BG", "https://gateway.example.com"),
    }
    calls = []
    mode = {"registry": "ok"}

    def registry_response(request):
        verify(request.content, parse(request.headers["authorization"]), seller_public)
        query = json.loads(request.content)
        calls.append(query)
        if mode["registry"] == "timeout":
            raise httpx.ReadTimeout("synthetic", request=request)
        if mode["registry"] == "bad":
            return httpx.Response(200, json={"unexpected": True})
        if mode["registry"] == "http":
            return httpx.Response(503)
        if mode["registry"] == "unknown" or query["subscriber_id"] not in records:
            return httpx.Response(200, json=[])
        public, key, kind, uri = records[query["subscriber_id"]]
        record = {"subscriber_id": query["subscriber_id"], "ukId": key, "subscriber_url": uri,
            "country": "IND", "domain": "ONDC:RET12", "city": "std:080", "type": kind,
            "status": "SUBSCRIBED", "signing_public_key": public,
            "valid_from": "2026-01-01T00:00:00Z", "valid_until": "2030-01-01T00:00:00Z"}
        if mode["registry"] == "wrong-key":
            record["ukId"] = "wrong"
        if mode["registry"] == "expired-key":
            record["valid_until"] = "2026-01-02T00:00:00Z"
        if mode["registry"] == "bad-key":
            record["signing_public_key"] = "bad"
        return httpx.Response(200, json=[record])

    registry = RegistryClient(settings, httpx.MockTransport(registry_response))
    signed_client = SignedClient(settings, httpx.ASGITransport(app=buyer.app))
    service = DiscoveryService(settings, registry, signed_client)
    purchase_service = PurchaseService(settings, registry, signed_client)
    post_order_service = PostOrderService(settings, registry, signed_client)
    def factory():
        return Session(engine, expire_on_commit=False, autoflush=False)
    def override():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = override
    app.state.ondc_service = service
    app.state.ondc_purchase_service = purchase_service
    app.state.ondc_post_order_service = post_order_service
    app.state.ondc_session_factory = factory
    app.state.admin_api_token = "test-admin-token"
    with TestClient(app) as client:
        seller = client.post("/api/sellers", json={"name": "SR Fashions", "email": "sales@sr-fashions.example.com"}).json()
        store = client.post("/api/stores", json={"seller_id": seller["id"], "name": "Main Store", "address": "Jayanagar, Bengaluru"}).json()
        variants = [{"sku": f"SR-SHIRT-{color.upper()}-{size}", "size": size, "color": color,
            "mrp": "1499.00", "selling_price": "1199.00", "store_id": store["id"], "initial_stock": 0 if color == "White" and size == "L" else 12}
            for color in ("Black", "White") for size in ("S", "M", "L")]
        product = client.post("/api/products", json={"seller_id": seller["id"], "name": "Men's Cotton Shirt",
            "brand": "SR Essentials", "description": "Cotton shirt with a tailored fit", "category": "Shirts", "variants": variants}).json()
        image = "https://seller.example.com/images/cotton-shirt.jpg"
        descriptor = {"name": "SR Fashions", "symbol": image, "short_desc": "Fashion retailer",
            "long_desc": "SR Fashions apparel collection", "images": [image]}
        provider = {"enabled": True, "metadata": {"bpp_descriptor": {**descriptor,
            "tags": [{"code": "bpp_terms", "list": [{"code": "np_type", "value": "ISN"}]}]},
            "provider_descriptor": descriptor, "provider_ttl": "P1D", "fulfillment_id": "F1",
            "fulfillment_type": "Delivery", "contact": {"phone": "18001234567", "email": "support@sr-fashions.example.com"},
            "category_mapping": {"Shirts": "Shirts"}}}
        location = f'store-{store["id"]}'
        store_meta = {"enabled": True, "delivery_charge": "49.00", "fulfillment_tat": "PT60M",
            "gps": "12.9250,77.5938", "address": {"locality": "Jayanagar", "street": "4th Block",
            "city": "Bengaluru", "state": "KA", "area_code": "560041"},
            "hours": {"start": "1000", "end": "2000"}, "tags": [
                {"code": "timing", "list": [{"code": k, "value": v} for k, v in {"type": "All", "location": location,
                    "day_from": "1", "day_to": "7", "time_from": "1000", "time_to": "2000"}.items()]},
                {"code": "serviceability", "list": [{"code": k, "value": v} for k, v in {"location": location,
                    "category": "Shirts", "type": "12", "val": "IND", "unit": "country"}.items()]}]}
        product_meta = {"images": [image], "attributes": {"gender": "male", "fabric": "cotton",
            "size_chart": "https://seller.example.com/images/shirt-size-chart.png"},
            "colour_hex_by_name": {"Black": "#000000", "White": "#FFFFFF"}, "origin_country": "IND",
            "statutory": {"manufacturer_or_packer_name": "SR Apparel", "manufacturer_or_packer_address": "Bengaluru, Karnataka",
                "common_or_generic_name_of_commodity": "Shirt", "month_year_of_manufacture_packing_import": "10/2026"},
            "returnable": True, "cancellable": True, "return_window": "P7D", "seller_pickup_return": True,
            "time_to_ship": "P1D", "available_on_cod": False,
            "consumer_care": "SR Care,support@sr-fashions.example.com,18001234567", "maximum_per_order": 5}
        for path, payload in [(f'/sellers/{seller["id"]}', provider), (f'/stores/{store["id"]}', store_meta),
                               (f'/products/{product["id"]}', product_meta)]:
            response = client.put("/api/ondc/publication" + path, json=payload)
            assert response.status_code == 200, response.text
        yield {"client": client, "factory": factory, "settings": settings, "service": service, "buyer": buyer,
            "registry": registry, "mode": mode, "calls": calls, "seller": seller, "store": store, "product": product,
            "purchase_service": purchase_service,
            "post_order_service": post_order_service,
            "provider": provider, "store_meta": store_meta, "product_meta": product_meta,
            "buyer_private": buyer_private, "buyer_public": buyer_public, "seller_public": seller_public,
            "gateway_private": gateway_private, "records": records}
    app.dependency_overrides.clear()
    del app.state.ondc_service
    del app.state.ondc_purchase_service
    del app.state.ondc_post_order_service
    del app.state.ondc_session_factory
    del app.state.admin_api_token
    engine.dispose()

def row(discovery):
    with discovery["factory"]() as db:
        return db.scalar(select(DiscoveryMessage))

def test_signed_local_discovery_end_to_end(discovery):
    buyer = discovery["buyer"]
    payload = buyer.search()
    response = buyer.send(discovery["client"], payload)
    assert response.status_code == 200
    assert len(buyer.callbacks) == 1
    callback = buyer.callbacks[0]
    assert callback["context"]["transaction_id"] == payload["context"]["transaction_id"]
    assert callback["context"]["message_id"] == payload["context"]["message_id"]
    items = callback["message"]["catalog"]["bpp/providers"][0]["items"]
    assert len(items) == 6
    assert {i["id"].split("@")[0] for i in items} == {f"SR-SHIRT-{c}-{s}" for c in ("BLACK", "WHITE") for s in ("S", "M", "L")}
    assert items[-1]["quantity"]["available"]["count"] == "0"
    assert all(i["price"] == {"currency": "INR", "value": "1199.00", "maximum_value": "1499.00"} for i in items)
    assert row(discovery).status == "delivered"

def test_duplicate_retry_ack_without_second_callback(discovery):
    buyer = discovery["buyer"]
    payload = buyer.search()
    buyer.send(discovery["client"], payload)
    buyer.send(discovery["client"], payload)
    assert len(buyer.callbacks) == 1
    assert row(discovery).attempts == 1
    assert len(discovery["calls"]) == 1

def test_identifier_reuse_with_changed_body(discovery):
    buyer = discovery["buyer"]
    payload = buyer.search()
    buyer.send(discovery["client"], payload)
    payload["message"]["intent"] = {}
    raw, headers = buyer.signed(payload)
    response = discovery["client"].post("/search", content=raw, headers=headers)
    assert response.json()["error"]["code"] == "30022"
    assert len(buyer.callbacks) == 1

@pytest.mark.parametrize("case", ["missing", "malformed", "invalid-signature", "unknown", "expired", "future",
    "bad-created", "tamper", "identity", "duplicate-header", "algorithm", "uri", "future-context",
    "expired-context", "invalid-timestamp", "domain", "context", "missing-ttl", "bad-json", "duplicate-json"])
def test_negative_inbound(discovery, case):
    buyer = discovery["buyer"]
    payload = buyer.search()
    if case == "future-context":
        payload["context"]["timestamp"] = "2099-01-01T00:00:00Z"
    elif case == "expired-context":
        payload["context"]["timestamp"] = "2020-01-01T00:00:00Z"
    elif case == "invalid-timestamp":
        payload["context"]["timestamp"] = "not-a-timestamp"
    elif case == "domain":
        payload["context"]["domain"] = "ONDC:RET10"
    elif case == "context":
        del payload["context"]["message_id"]
    elif case == "missing-ttl":
        del payload["context"]["ttl"]
    elif case == "uri":
        payload["context"]["bap_uri"] = "https://buyer.example.com/private"
    raw, headers = buyer.signed(payload)
    if case == "missing":
        del headers["Authorization"]
    elif case == "malformed":
        headers["Authorization"] = "Bearer invalid"
    elif case == "invalid-signature":
        headers["Authorization"] = headers["Authorization"].replace('signature="', 'signature="A', 1)
    elif case == "unknown":
        discovery["mode"]["registry"] = "unknown"
    elif case in ("expired", "future"):
        created = int(time.time()) + (120 if case == "future" else -120)
        headers["Authorization"] = sign(raw, subscriber_id="buyer.example.com", key_id="buyer-key",
            private=discovery["buyer_private"], created=created, expires=created+30)
    elif case == "bad-created":
        headers["Authorization"] = headers["Authorization"].replace('created="', 'created="X')
    elif case == "tamper":
        raw = raw.replace(b"local-fashion-T1", b"tampered-fashion")
    elif case == "identity":
        headers["Authorization"] = headers["Authorization"].replace("buyer.example.com|", "imposter.example.com|")
    elif case == "duplicate-header":
        headers["Authorization"] += ',algorithm="ed25519"'
    elif case == "algorithm":
        headers["Authorization"] = headers["Authorization"].replace('algorithm="ed25519"', 'algorithm="rsa"')
    elif case == "bad-json":
        raw = b"{"
    elif case == "duplicate-json":
        raw = b'{"context":{},"context":{},"message":{}}'
    response = discovery["client"].post("/search", content=raw, headers=headers)
    assert response.json()["message"]["ack"]["status"] == "NACK"
    if case in ("missing", "malformed", "invalid-signature", "unknown", "expired", "future", "bad-created",
                "tamper", "identity", "duplicate-header", "algorithm", "uri"):
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "30016"
    assert not buyer.callbacks
    assert row(discovery) is None

@pytest.mark.parametrize("mode", ["timeout", "bad", "http", "wrong-key", "expired-key", "bad-key"])
def test_registry_failures(discovery, mode):
    discovery["mode"]["registry"] = mode
    raw, headers = discovery["buyer"].signed(discovery["buyer"].search())
    response = discovery["client"].post("/search", content=raw, headers=headers)
    assert response.json()["message"]["ack"]["status"] == "NACK"
    assert response.status_code == (401 if mode in ("wrong-key", "expired-key") else 503)
    assert row(discovery) is None

def test_gateway_signature_required_and_verified(discovery):
    discovery["settings"].allow_local_peer_search = False
    buyer = discovery["buyer"]
    payload = buyer.search()
    raw, headers = buyer.signed(payload)
    assert discovery["client"].post("/search", content=raw, headers=headers).status_code == 401
    headers["X-Gateway-Authorization"] = sign(raw, subscriber_id="gateway.example.com", key_id="gateway-key",
                                              private=discovery["gateway_private"])
    assert discovery["client"].post("/search", content=raw, headers=headers).json()["message"]["ack"]["status"] == "ACK"
    assert len(buyer.callbacks) == 1

@pytest.mark.parametrize("mode", ["timeout", "http", "nack", "malformed"])
def test_callback_failure_persisted_and_retry_recovers(discovery, mode):
    def failure(request):
        if mode == "timeout":
            raise httpx.ReadTimeout("synthetic", request=request)
        if mode == "http":
            return httpx.Response(500)
        if mode == "malformed":
            return httpx.Response(200, json={"unexpected": True})
        return httpx.Response(200, json={"message": {"ack": {"status": "NACK"}},
                     "error": {"type": "DOMAIN-ERROR", "code": "30000"}})
    service = discovery["service"]
    original = service.client
    service.client = SignedClient(discovery["settings"], httpx.MockTransport(failure))
    buyer = discovery["buyer"]
    payload = buyer.search()
    buyer.send(discovery["client"], payload)
    assert row(discovery).status == "failed"
    assert row(discovery).error == ("callback_rejected" if mode == "nack" else "callback_failed")
    if mode == "nack":
        with discovery["factory"]() as db:
            assert {state.state for state in db.scalars(select(CatalogPublicationState))} == {"rejected"}
    service.client = original
    # Recovery does not require receiving a fresh request or repeating catalog mapping.
    with discovery["factory"]() as db:
        asyncio.run(service.resume(db))
    assert row(discovery).status == "delivered"
    assert row(discovery).attempts == 2
    assert len(buyer.callbacks) == 1

def test_invalid_publication_catalog_never_acknowledged(discovery):
    with discovery["factory"]() as db:
        metadata = db.get(ProductPublicationRow, discovery["product"]["id"])
        metadata.data = {**metadata.data, "attributes": {"gender": "male"}}
        db.commit()
    raw, headers = discovery["buyer"].signed(discovery["buyer"].search())
    response = discovery["client"].post("/search", content=raw, headers=headers)
    assert response.json()["message"]["ack"]["status"] == "NACK"
    assert not discovery["buyer"].callbacks
    assert row(discovery) is None

def test_metadata_read_roundtrip_and_secret_rejection(discovery):
    client = discovery["client"]
    for kind in ("seller", "store", "product"):
        identity = discovery[kind]["id"]
        response = client.get(f"/api/ondc/publication/{kind}s/{identity}")
        assert response.status_code == 200
        assert "private" not in response.text
    payload = {**discovery["provider"], "signing_private_key": "do-not-expose"}
    response = client.put(f'/api/ondc/publication/sellers/{discovery["seller"]["id"]}', json=payload)
    assert response.status_code == 422
    assert "do-not-expose" not in response.text

@pytest.mark.parametrize("field,value", [("gps", "95.0000,77.0000"), ("gps", "12,77"),
    ("address", {"city": "Bengaluru"}), ("hours", {"start": "2500", "end": "2000"})])
def test_metadata_invalid_input(discovery, field, value):
    response = discovery["client"].put(f'/api/ondc/publication/stores/{discovery["store"]["id"]}',
                            json={**discovery["store_meta"], field: value})
    assert response.status_code == 422

def test_replay_lease_and_cleanup(discovery):
    buyer = discovery["buyer"]
    buyer.send(discovery["client"], buyer.search())
    with discovery["factory"]() as db:
        message = db.scalar(select(DiscoveryMessage))
        message.status = "sending"
        message.lease_until = time.time() + 60
        db.commit()
        asyncio.run(discovery["service"].dispatch(db, message.id))
        assert db.get(DiscoveryMessage, message.id).attempts == 1
        message.status = "delivered"
        message.retain_until = time.time() - 1
        db.commit()
        assert cleanup(db) == 1

def test_crypto_reference_interoperability():
    private, public = generate_keys()
    raw = '{"message":"cotton shirt ₹"}'.encode()
    assert len(base64.b64decode(private)) == 64
    assert len(base64.b64decode(public)) == 32
    auth = parse(sign(raw, subscriber_id="seller.example.com", key_id="k1", private=private, created=100, expires=130))
    verify(raw, auth, public, now=110)
    from nacl.hash import blake2b
    from nacl.encoding import Base64Encoder
    assert digest(raw) == blake2b(raw, digest_size=64, encoder=Base64Encoder).decode()
    assert signing_string(raw, 100, 130) == f"(created): 100\n(expires): 130\ndigest: BLAKE-512={digest(raw)}".encode()
    with pytest.raises(SignatureError):
        verify(raw+b" ", auth, public, now=110)
    with pytest.raises(SignatureError):
        private_key(base64.b64encode(b"x"*64).decode())

def purchase_payloads(discovery, transaction="purchase-T1"):
    buyer = discovery["buyer"]
    store_id = discovery["store"]["id"]
    item_id = f'{discovery["product"]["variants"][0]["sku"]}@store-{store_id}'
    provider = {"id": f'seller-{discovery["seller"]["id"]}', "locations": [{"id": f"store-{store_id}"}]}
    end = {"location": {"gps": "12.9300,77.5900", "address": {"area_code": "560041"}}}
    payload = {"context": buyer.context("select", transaction, "select-M1"), "message": {"order": {
        "provider": provider, "items": [{"id": item_id, "quantity": {"count": 2},
        "location_id": f"store-{store_id}"}], "fulfillments": [{"end": end}]}}}
    return buyer, provider, end, item_id, payload

def complete_purchase(discovery, transaction="purchase-T1", order_id="ORDER-1"):
    buyer, provider, end, item_id, select_payload = purchase_payloads(discovery, transaction)
    response = buyer.send_action(discovery["client"], "select", select_payload)
    assert response.json() == {"message": {"ack": {"status": "ACK"}}}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    billing = {"address": {"building": "12", "locality": "Jayanagar", "city": "Bengaluru",
        "state": "KA", "country": "IND", "area_code": "560041"}, "phone": "9999999999",
        "name": "Test Buyer", "email": "buyer@example.com", "created_at": now, "updated_at": now}
    fulfillment = {"id": "F1", "type": "Delivery", "end": {**end,
        "contact": {"phone": "9999999999", "email": "buyer@example.com"}, "person": {"name": "Test Buyer"}}}
    init_payload = {"context": buyer.context("init", transaction, "init-M1"), "message": {"order": {
        "provider": provider, "items": [{"id": item_id, "quantity": {"count": 2},
        "location_id": provider["locations"][0]["id"], "fulfillment_id": "F1"}],
        "billing": billing, "fulfillments": [fulfillment]}}}
    response = buyer.send_action(discovery["client"], "init", init_payload)
    assert response.json() == {"message": {"ack": {"status": "ACK"}}}
    quote = buyer.callbacks[-1]["message"]["order"]["quote"]
    confirm_payload = {"context": buyer.context("confirm", transaction, "confirm-M1"), "message": {"order": {
        "id": order_id, "state": "Created", "provider": provider,
        "items": [{"id": item_id, "quantity": {"count": 2}, "location_id": provider["locations"][0]["id"],
                   "fulfillment_id": "F1"}], "billing": billing, "fulfillments": [fulfillment],
        "quote": quote, "payment": {"params": {"amount": quote["price"]["value"], "currency": "INR",
        "transaction_id": "PAY-1"}, "status": "PAID", "type": "ON-ORDER", "collected_by": "BAP"},
        "created_at": now, "updated_at": now}}}
    response = buyer.send_action(discovery["client"], "confirm", confirm_payload)
    return response, confirm_payload

def test_complete_signed_purchase_flow_and_admin_order(discovery):
    before = discovery["client"].get("/api/inventory", params={"store_id": discovery["store"]["id"]}).json()[0]["quantity"]
    response, confirm_payload = complete_purchase(discovery)
    assert response.json() == {"message": {"ack": {"status": "ACK"}}}
    assert [row["context"]["action"] for row in discovery["buyer"].callbacks[-3:]] == ["on_select", "on_init", "on_confirm"]
    callback = discovery["buyer"].callbacks[-1]
    assert callback["context"]["transaction_id"] == "purchase-T1"
    assert callback["context"]["message_id"] == "confirm-M1"
    assert callback["message"]["order"]["state"] == "Accepted"
    after = discovery["client"].get("/api/inventory", params={"store_id": discovery["store"]["id"]}).json()[0]["quantity"]
    assert after == before - 2
    orders = discovery["client"].get("/api/ondc/orders").json()
    assert orders[0]["id"] == "ORDER-1" and orders[0]["source"] == "ONDC"
    assert orders[0]["payment_status"] == "PAID" and orders[0]["items"][0]["quantity"] == 2

def test_purchase_duplicate_requests_are_idempotent(discovery):
    response, confirm_payload = complete_purchase(discovery, "purchase-duplicate", "ORDER-D")
    assert response.json()["message"]["ack"]["status"] == "ACK"
    callbacks = len(discovery["buyer"].callbacks)
    response = discovery["buyer"].send_action(discovery["client"], "confirm", confirm_payload)
    assert response.json()["message"]["ack"]["status"] == "ACK"
    assert len(discovery["buyer"].callbacks) == callbacks
    assert len(discovery["client"].get("/api/ondc/orders").json()) == 1

@pytest.mark.parametrize("case,code", [("missing", "30004"), ("stock", "40002"), ("quantity", "40009"), ("destination", "30009")])
def test_select_business_rejections(discovery, case, code):
    buyer, provider, end, item_id, payload = purchase_payloads(discovery, "reject-" + case)
    if case == "missing": payload["message"]["order"]["items"][0]["id"] = "NO-SKU@store-1"
    if case == "stock":
        payload["message"]["order"]["items"][0]["id"] = f'SR-SHIRT-WHITE-L@store-{discovery["store"]["id"]}'
    if case == "quantity": payload["message"]["order"]["items"][0]["quantity"]["count"] = 6
    if case == "destination":
        discovery["store_meta"]["tags"][1]["list"] = [{"code": k, "value": v} for k, v in {
            "location": f'store-{discovery["store"]["id"]}', "category": "Shirts", "type": "11",
            "val": "999999", "unit": "pincode"}.items()]
        discovery["client"].put(f'/api/ondc/publication/stores/{discovery["store"]["id"]}', json=discovery["store_meta"])
    response = buyer.send_action(discovery["client"], "select", payload)
    assert response.json()["error"]["code"] == code

def test_disabled_store_and_catalog_rejection_state(discovery):
    meta = dict(discovery["store_meta"])
    meta["enabled"] = False
    assert discovery["client"].put(f'/api/ondc/publication/stores/{discovery["store"]["id"]}', json=meta).status_code == 200
    states = discovery["client"].get("/api/ondc/catalog-state").json()
    assert next(row for row in states if row["entity_type"] == "store")["state"] == "pending"
    response = discovery["client"].put(f'/api/ondc/catalog-state/store/{discovery["store"]["id"]}/rejection',
        json={"code": "CATALOG-INVALID", "message": "Rejected by mock buyer"},
        headers={"X-Admin-Token": "test-admin-token"})
    assert response.json()["state"] == "rejected"
    payload = discovery["buyer"].search(transaction="disabled-T", message="disabled-M")
    raw, headers = discovery["buyer"].signed(payload)
    response = discovery["client"].post("/search", content=raw, headers=headers)
    assert response.json()["message"]["ack"]["status"] == "NACK"

def test_incremental_catalog_changed_item_and_empty_window(discovery):
    buyer = discovery["buyer"]
    with discovery["factory"]() as db:
        variants = db.scalars(select(ProductVariant)).all()
        inventories = db.scalars(select(Inventory)).all()
        products = db.scalars(select(Product)).all()
        old = datetime(2026, 1, 1)
        for row in [*products, *variants, *inventories]:
            row.updated_at = old
        for state in db.scalars(select(CatalogPublicationState)):
            state.changed_at = old.replace(tzinfo=timezone.utc).timestamp()
        variants[0].selling_price = Decimal("1099.00")
        variants[0].updated_at = datetime.now(timezone.utc)
        db.commit()
    start = (datetime.now(timezone.utc).timestamp() - 60)
    end = start + 120
    def iso(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")
    payload = buyer.search(transaction="inc-T", message="inc-M")
    payload["message"]["intent"]["tags"] = [{"code": "catalog_inc", "list": [
        {"code": "start_time", "value": iso(start)}, {"code": "end_time", "value": iso(end)}]}]
    response = buyer.send(discovery["client"], payload)
    assert response.json()["message"]["ack"]["status"] == "ACK"
    items = buyer.callbacks[-1]["message"]["catalog"]["bpp/providers"][0]["items"]
    assert len(items) == 1 and items[0]["price"]["value"] == "1099.00"
    assert buyer.callback_headers[-1]["x-ondc-search-response"] == "inc"
    count = len(buyer.callbacks)
    payload = buyer.search(transaction="inc-empty-T", message="inc-empty-M")
    payload["message"]["intent"]["tags"] = [{"code": "catalog_inc", "list": [
        {"code": "start_time", "value": "2025-01-01T00:00:00Z"},
        {"code": "end_time", "value": "2025-01-01T01:00:00Z"}]}]
    response = buyer.send(discovery["client"], payload)
    assert response.json()["message"]["ack"]["status"] == "ACK"
    assert len(buyer.callbacks) == count

def test_incremental_push_mode_creates_durable_subscription(discovery):
    payload = discovery["buyer"].search(transaction="inc-push-T", message="inc-push-M")
    payload["message"]["intent"]["tags"] = [{"code": "catalog_inc", "list": [{"code": "mode", "value": "start"}]}]
    raw, headers = discovery["buyer"].signed(payload)
    response = discovery["client"].post("/search", content=raw, headers=headers)
    assert response.json()["message"]["ack"]["status"] == "ACK"
    sync = discovery["client"].get("/api/ondc/catalog-sync").json()
    assert len(sync["subscriptions"]) == 1
    assert sync["subscriptions"][0]["status"] == "active"

def test_registry_cache_expires(discovery):
    registry = discovery["registry"]
    asyncio.run(registry.lookup("buyer.example.com", "buyer-key"))
    asyncio.run(registry.lookup("buyer.example.com", "buyer-key"))
    assert len(discovery["calls"]) == 1
    registry.cache = {}
    asyncio.run(registry.lookup("buyer.example.com", "buyer-key"))
    assert len(discovery["calls"]) == 2


def test_finder_fee_policy_and_buyer_terms(discovery):
    buyer = discovery["buyer"]
    payload = buyer.search(message="fee-search")
    payload["message"]["intent"]["payment"] = {
        "@ondc/org/buyer_app_finder_fee_type": "percent",
        "@ondc/org/buyer_app_finder_fee_amount": "3.54"}
    raw, headers = buyer.signed(payload)
    assert discovery["client"].post("/search", content=raw, headers=headers).json()["error"]["code"] == "41001"
    provider = json.loads(json.dumps(discovery["provider"]))
    provider["metadata"]["finder_fee_policy"] = {
        "finder_fee_type": "percent", "finder_fee_amount_min": "0", "finder_fee_amount_max": "4"}
    assert discovery["client"].put(f'/api/ondc/publication/sellers/{discovery["seller"]["id"]}', json=provider).status_code == 200
    buyer.send(discovery["client"], payload)
    payload = buyer.search(message="terms-search")
    payload["message"]["intent"]["tags"] = [
        {"code": "bap_terms", "list": [{"code": "static_terms_new", "value": "https://buyer.example.com/terms"}]}]
    raw, headers = buyer.signed(payload)
    assert discovery["client"].post("/search", content=raw, headers=headers).json()["error"]["code"] == "50005"
    provider["metadata"]["bpp_descriptor"]["tags"][0]["list"].append({"code": "accept_bap_terms", "value": "Y"})
    assert discovery["client"].put(f'/api/ondc/publication/sellers/{discovery["seller"]["id"]}', json=provider).status_code == 200
    buyer.send(discovery["client"], payload)
    assert len(buyer.callbacks) == 2

def test_invalid_taxonomy_metadata_rejected(discovery):
    provider = json.loads(json.dumps(discovery["provider"]))
    provider["metadata"]["category_mapping"]["Shirts"] = "Invented Fashion Code"
    response = discovery["client"].put(f'/api/ondc/publication/sellers/{discovery["seller"]["id"]}', json=provider)
    assert response.status_code == 422

def test_callback_expiry_stops_recovery(discovery):
    buyer = discovery["buyer"]
    buyer.send(discovery["client"], buyer.search())
    with discovery["factory"]() as db:
        message = db.scalar(select(DiscoveryMessage))
        callback = json.loads(json.dumps(message.callback))
        callback["context"]["timestamp"] = "2020-01-01T00:00:00Z"
        for provider in callback["message"]["catalog"]["bpp/providers"]:
            provider["time"]["timestamp"] = "2020-01-01T00:00:00Z"
            for entry in provider["locations"] + provider["items"]:
                entry["time"]["timestamp"] = "2020-01-01T00:00:00Z"
        message.callback = callback
        message.status = "failed"
        db.commit()
        asyncio.run(discovery["service"].resume(db))
        db.refresh(message)
        assert message.status == "expired"
        assert message.error == "callback_expired"
        assert len(buyer.callbacks) == 1
        attempts = message.attempts
        asyncio.run(discovery["service"].resume(db))
        db.refresh(message)
        assert message.attempts == attempts

@pytest.mark.parametrize("mutate", ["body", "unknown-key"])
def test_invalid_gateway_signature(discovery, mutate):
    buyer = discovery["buyer"]
    raw, headers = buyer.signed(buyer.search())
    headers["X-Gateway-Authorization"] = sign(raw + (b" " if mutate == "body" else b""),
        subscriber_id="gateway.example.com", key_id="gateway-key" if mutate == "body" else "wrong",
        private=discovery["gateway_private"])
    response = discovery["client"].post("/search", content=raw, headers=headers)
    assert response.status_code == 401
    assert not buyer.callbacks

def test_external_and_production_calls_disabled(discovery):
    client = SignedClient(discovery["settings"])
    with pytest.raises(CallbackError, match="External communication disabled"):
        asyncio.run(client.post("https://buyer.example.com/ondc/on_search", {}))
    client = SignedClient(discovery["settings"], httpx.MockTransport(lambda _: pytest.fail("Production called")))
    with pytest.raises(CallbackError, match="Production communication disabled"):
        asyncio.run(client.post("https://prod.registry.ondc.org/v2.0/lookup", {}))

@pytest.mark.parametrize("address", ["127.0.0.1", "169.254.169.254", "::1"])
def test_private_callback_destination_rejected(discovery, monkeypatch, address):
    from app.ondc.signing.security import check_destination
    discovery["settings"].allow_local_callbacks = False
    monkeypatch.setattr("socket.getaddrinfo", lambda *args: [(2, 1, 6, "", (address, 443))])
    with pytest.raises(SignatureError):
        asyncio.run(check_destination("https://buyer.example.com/ondc", discovery["settings"]))

def test_config_route_prefix_and_development_gates():
    from app.ondc.config import RouteSettings
    assert RouteSettings(_env_file=None, route_prefix="/ondc/").route_prefix == "/ondc"
    with pytest.raises(ValidationError):
        RouteSettings(_env_file=None, route_prefix="/../api")
    with pytest.raises(ValidationError):
        ONDCSettings(_env_file=None, environment="preprod", subscriber_id="seller.example.com",
            subscriber_url="https://seller.example.com", callback_url="https://seller.example.com",
            unique_key_id="k1", city="std:080", allow_local_peer_search=True)

def test_real_loopback_http_discovery(discovery):
    """Actual sockets: search ACK precedes independently received signed gzip callback."""
    import socket
    import threading
    import uvicorn
    from contextlib import ExitStack
    servers, threads, sockets = [], [], []
    try:
        for target in (app, None):
            sock = socket.socket()
            sock.bind(("127.0.0.1", 0))
            sockets.append(sock)
        seller_port, buyer_port = [s.getsockname()[1] for s in sockets]
        buyer_uri = f"http://127.0.0.1:{buyer_port}/ondc"
        buyer = MockBuyer(discovery["buyer_private"], discovery["seller_public"],
                          subscriber_id="127.0.0.1", subscriber_url=buyer_uri)
        settings = discovery["settings"]
        settings.subscriber_id = "localhost"
        settings.subscriber_url = f"http://localhost:{seller_port}"
        settings.callback_url = settings.subscriber_url
        discovery["records"]["127.0.0.1"] = (discovery["buyer_public"], "buyer-key", "BAP", buyer_uri)
        discovery["service"].client = SignedClient(settings)
        for target, sock in zip((app, buyer.app), sockets):
            server = uvicorn.Server(uvicorn.Config(target, host="127.0.0.1", log_level="error",
                                    access_log=False, lifespan="off"))
            thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
            server.install_signal_handlers = lambda: None
            servers.append(server)
            threads.append(thread)
            thread.start()
        deadline = time.monotonic() + 5
        while not all(s.started for s in servers):
            assert time.monotonic() < deadline, "Local test servers failed to start"
            time.sleep(0.01)
        payload = buyer.search(transaction="loopback-T1", message="loopback-M1")
        raw, headers = buyer.signed(payload)
        response = httpx.post(f"http://127.0.0.1:{seller_port}/search", content=raw, headers=headers, timeout=5)
        assert response.json() == {"message": {"ack": {"status": "ACK"}}}
        while not buyer.callbacks:
            assert time.monotonic() < deadline, "Callback not delivered"
            time.sleep(0.01)
        assert len(buyer.callbacks[0]["message"]["catalog"]["bpp/providers"][0]["items"]) == 6
        assert buyer.callbacks[0]["context"]["transaction_id"] == "loopback-T1"
        assert buyer.callbacks[0]["context"]["message_id"] == "loopback-M1"
    finally:
        for server in servers:
            server.should_exit = True
        for thread in threads:
            thread.join(timeout=5)
            assert not thread.is_alive()
        for sock in sockets:
            sock.close()

def test_database_replay_uniqueness_across_sessions(discovery, tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.ondc.protocol.replay import accept
    engine = create_engine("sqlite:///" + str(tmp_path / "replay.db"), connect_args={"timeout": 5})
    Base.metadata.create_all(engine)
    payload = discovery["buyer"].search()
    search = validate_search(payload)
    raw = serialize(payload)
    with discovery["factory"]() as db:
        callback, callback_headers, no_changes = build_callback(db, search, discovery["settings"])
    def worker(_):
        with Session(engine) as db:
            return accept(db, search, raw, callback, discovery["settings"], callback_headers=callback_headers).id
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(worker, range(2)))
    assert ids[0] == ids[1]
    with Session(engine) as db:
        assert len(db.scalars(select(DiscoveryMessage)).all()) == 1
    engine.dispose()

def test_development_key_utility_keeps_private_key_out_of_stdout(tmp_path):
    import subprocess
    import sys
    path = tmp_path / ".env"
    result = subprocess.run([sys.executable, "-m", "app.ondc.signing.generate", "--output", str(path)],
                            capture_output=True, text=True, check=True)
    private = path.read_text().splitlines()[0].split("=", 1)[1]
    assert len(base64.b64decode(private)) == 64
    assert private not in result.stdout + result.stderr
    result = subprocess.run([sys.executable, "-m", "app.ondc.signing.generate", "--output", str(path)],
                            capture_output=True, text=True)
    assert result.returncode != 0  # Existing material is never overwritten.


def test_official_python_utility_sign_verify_interoperability():
    """Run only four pinned reference helpers, without its CLI, imports or file I/O."""
    import ast
    import datetime as datetime_module
    import nacl.hash
    import nacl.encoding
    from nacl.bindings import crypto_sign_ed25519_sk_to_seed
    from nacl.signing import SigningKey, VerifyKey
    source = Path(__file__).parents[1] / "app/ondc/protocol/spec/signing-reference.py.txt"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    selected = {"hash_message", "create_signing_string", "sign_response", "verify_response"}
    helpers = ast.Module(body=[node for node in tree.body if isinstance(node, ast.FunctionDef)
                               and node.name in selected], type_ignores=[])
    namespace = {"base64": base64, "datetime": datetime_module, "nacl": nacl,
                 "SigningKey": SigningKey, "VerifyKey": VerifyKey,
                 "crypto_sign_ed25519_sk_to_seed": crypto_sign_ed25519_sk_to_seed}
    exec(compile(helpers, str(source), "exec"), namespace)
    private, public = generate_keys()
    raw = serialize({"message": "SR Fashions cotton shirt"})
    official_digest = namespace["hash_message"](raw.decode())
    official_string = namespace["create_signing_string"](official_digest, 100, 130)
    assert signing_string(raw, 100, 130).decode() == official_string
    auth = parse(sign(raw, subscriber_id="seller.example.com", key_id="k1",
                      private=private, created=100, expires=130))
    assert namespace["verify_response"](auth.signature, official_string, public)
    official_signature = namespace["sign_response"](official_string, private)
    assert official_signature == auth.signature
    verify(raw, auth, public, now=110)

def post_context(buyer, action, transaction, message):
    return buyer.context(action, transaction, message)

def test_status_signed_callback_unknown_and_duplicate(discovery):
    complete_purchase(discovery, "status-T", "ORDER-STATUS")
    buyer = discovery["buyer"]
    payload = {"context": post_context(buyer, "status", "status-T", "status-M"),
               "message": {"order_id": "ORDER-STATUS"}}
    response = buyer.send_action(discovery["client"], "status", payload)
    assert response.json()["message"]["ack"]["status"] == "ACK"
    callback = buyer.callbacks[-1]
    assert callback["context"]["action"] == "on_status"
    assert callback["message"]["order"]["state"] == "Accepted"
    count = len(buyer.callbacks)
    assert buyer.send_action(discovery["client"], "status", payload).json()["message"]["ack"]["status"] == "ACK"
    assert len(buyer.callbacks) == count
    missing = {"context": post_context(buyer, "status", "missing-T", "missing-M"),
               "message": {"order_id": "UNKNOWN"}}
    assert buyer.send_action(discovery["client"], "status", missing).json()["error"]["code"] == "30018"

def test_admin_fulfillment_auth_transitions_and_history(discovery):
    complete_purchase(discovery, "admin-T", "ORDER-ADMIN")
    url = "/api/ondc/orders/ORDER-ADMIN/transitions"
    assert discovery["client"].post(url, json={"target": "packed", "idempotency_key": "pack-1"}).status_code == 401
    headers = {"X-Admin-Token": "test-admin-token"}
    first = discovery["client"].post(url, json={"target": "packed", "idempotency_key": "pack-1"}, headers=headers)
    assert first.json()["fulfillment_state"] == "Packed"
    repeated = discovery["client"].post(url, json={"target": "packed", "idempotency_key": "pack-1"}, headers=headers)
    assert repeated.status_code == 200
    assert discovery["client"].post(url, json={"target": "delivered", "idempotency_key": "bad"}, headers=headers).status_code == 409
    for target in ["ready_for_pickup", "picked_up", "delivered"]:
        response = discovery["client"].post(url, json={"target": target, "idempotency_key": target}, headers=headers)
        assert response.status_code == 200
    order = discovery["client"].get("/api/ondc/orders").json()[0]
    assert order["state"] == "Completed" and order["fulfillment_state"] == "Order-delivered"
    assert [event["to_state"] for event in order["history"]] == ["accepted", "packed", "ready_for_pickup", "picked_up", "delivered"]

def test_cancel_tat_inventory_and_refund_idempotency(discovery):
    complete_purchase(discovery, "cancel-T", "ORDER-CANCEL")
    buyer = discovery["buyer"]
    payload = {"context": post_context(buyer, "cancel", "cancel-T", "cancel-M"), "message": {
        "order_id": "ORDER-CANCEL", "cancellation_reason_id": "006",
        "descriptor": {"name": "fulfillment", "short_desc": "F1"}}}
    early = buyer.send_action(discovery["client"], "cancel", payload)
    assert early.json()["error"]["code"] == "30014"
    with discovery["factory"]() as db:
        order = db.get(ONDCOrder, "ORDER-CANCEL")
        order.created_at -= 7200
        db.commit()
    before = discovery["client"].get("/api/inventory", params={"store_id": discovery["store"]["id"]}).json()[0]["quantity"]
    payload["context"]["message_id"] = "cancel-M2"
    payload["context"]["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    buyer.expected.add(("cancel-T", "cancel-M2"))
    response = buyer.send_action(discovery["client"], "cancel", payload)
    assert response.json()["message"]["ack"]["status"] == "ACK"
    assert buyer.callbacks[-1]["message"]["order"]["state"] == "Cancelled"
    after = discovery["client"].get("/api/inventory", params={"store_id": discovery["store"]["id"]}).json()[0]["quantity"]
    assert after == before + 2
    count = len(discovery["client"].get("/api/ondc/orders").json()[0]["financial_events"])
    assert buyer.send_action(discovery["client"], "cancel", payload).json()["message"]["ack"]["status"] == "ACK"
    assert discovery["client"].get("/api/inventory", params={"store_id": discovery["store"]["id"]}).json()[0]["quantity"] == after
    assert len(discovery["client"].get("/api/ondc/orders").json()[0]["financial_events"]) == count

def test_return_update_and_authenticated_decision(discovery):
    complete_purchase(discovery, "return-T", "ORDER-RETURN")
    headers = {"X-Admin-Token": "test-admin-token"}
    url = "/api/ondc/orders/ORDER-RETURN/transitions"
    for target in ["packed", "picked_up", "delivered"]:
        assert discovery["client"].post(url, json={"target": target, "idempotency_key": target}, headers=headers).status_code == 200
    item_id = f'{discovery["product"]["variants"][0]["sku"]}@store-{discovery["store"]["id"]}'
    payload = {"context": post_context(discovery["buyer"], "update", "return-T", "return-M"), "message": {
        "update_target": "item", "order": {"id": "ORDER-RETURN", "fulfillments": [{"type": "Return",
        "tags": [{"code": "return_request", "list": [
            {"code": "id", "value": "R1"}, {"code": "item_id", "value": item_id},
            {"code": "item_quantity", "value": "1"}, {"code": "reason_id", "value": "003"},
            {"code": "reason_desc", "value": "Size does not fit"}]}]}]}}}
    response = discovery["buyer"].send_action(discovery["client"], "update", payload)
    assert response.json()["message"]["ack"]["status"] == "ACK"
    assert discovery["buyer"].callbacks[-1]["message"]["order"]["fulfillments"][-1]["state"]["descriptor"]["code"] == "Return_Initiated"
    decision = "/api/ondc/orders/ORDER-RETURN/returns/R1/decision"
    assert discovery["client"].post(decision, json={"decision": "approve"}).status_code == 401
    assert discovery["client"].post(decision, json={"decision": "approve"}, headers=headers).json()["state"] == "Return_Approved"

def test_catalog_scheduler_recovery_and_duplicate_prevention(discovery):
    import httpx
    from app.ondc.catalog.scheduler import schedule_due, dispatch_due
    from app.ondc.clients.http import SignedClient
    payload = discovery["buyer"].search(transaction="sync-T", message="sync-start")
    payload["message"]["intent"]["tags"] = [{"code": "catalog_inc", "list": [{"code": "mode", "value": "start"}]}]
    raw, headers = discovery["buyer"].signed(payload)
    assert discovery["client"].post("/search", content=raw, headers=headers).json()["message"]["ack"]["status"] == "ACK"
    with discovery["factory"]() as db:
        sub = db.scalar(select(CatalogSubscription))
        inventory = db.scalar(select(Inventory))
        inventory.quantity += 1
        inventory.updated_at = datetime.now(timezone.utc)
        sub.next_run_at = time.time() - 1
        db.commit()
        assert schedule_due(db) == 1
        assert schedule_due(db) == 0
    calls = []
    def receiver(request):
        calls.append(request)
        return httpx.Response(200, json={"message": {"ack": {"status": "ACK"}}})
    client = SignedClient(discovery["settings"], httpx.MockTransport(receiver))
    with discovery["factory"]() as db:
        assert asyncio.run(dispatch_due(db, discovery["settings"], client)) == 1
    with discovery["factory"]() as db:
        job = db.scalar(select(CatalogPublicationJob))
        assert job.status == "delivered" and job.attempts == 1
    assert len(calls) == 1
