from copy import deepcopy
import pytest
from sqlalchemy.exc import OperationalError
from app.database import get_db
from app.main import app

def test_health_and_root(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}
    assert client.get("/").status_code == 200

def test_health_database_unavailable(client):
    def broken():
        raise OperationalError("SELECT 1", {}, Exception("private connection detail"))
        yield
    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = broken
    response = client.get("/health")
    app.dependency_overrides[get_db] = previous
    assert response.status_code == 503
    assert "private" not in response.text

def test_complete_product_inventory_lifecycle(client, catalog):
    seller, store, payload = catalog
    response = client.post("/api/products", json=payload)
    assert response.status_code == 201, response.text
    product = response.json()
    assert product["variants"][0]["selling_price"] == "999.00"
    assert product["created_at"]
    assert client.get(f"/api/products/{product['id']}").json()["name"] == "Shirt"
    assert len(client.get("/api/products").json()) == 1
    updated = {key: payload[key] for key in ["name", "brand", "description", "category"]}
    updated["name"] = "Updated shirt"
    assert client.put(f"/api/products/{product['id']}", json=updated).json()["name"] == "Updated shirt"
    inventory = client.get("/api/inventory").json()[0]
    assert inventory["quantity"] == 5
    assert client.put(f"/api/inventory/{inventory['id']}", json={"quantity": 8}).json()["quantity"] == 8
    assert client.delete(f"/api/stores/{store['id']}").status_code == 409
    assert client.delete(f"/api/sellers/{seller['id']}").status_code == 409
    assert client.delete(f"/api/products/{product['id']}").status_code == 204
    assert client.get("/api/inventory").json() == []
    assert client.get(f"/api/products/{product['id']}").status_code == 404
    assert client.delete(f"/api/stores/{store['id']}").status_code == 204
    assert client.delete(f"/api/sellers/{seller['id']}").status_code == 204

@pytest.mark.parametrize("field,value", [("selling_price", "1200.01"), ("mrp", "-1"), ("selling_price", "1.001"), ("initial_stock", -1), ("initial_stock", 1.5), ("initial_stock", 2147483648), ("sku", " "), ("size", "")])
def test_invalid_variant(client, catalog, field, value):
    payload = deepcopy(catalog[2])
    payload["variants"][0][field] = value
    assert client.post("/api/products", json=payload).status_code == 422
    assert client.get("/api/products").json() == []

def test_duplicate_sku_rolls_back_entire_product(client, catalog):
    payload = catalog[2]
    payload["variants"].append(deepcopy(payload["variants"][0]))
    assert client.post("/api/products", json=payload).status_code == 409
    assert client.get("/api/products").json() == []
    assert client.get("/api/inventory").json() == []

def test_cross_seller_stock_rejected(client, catalog):
    seller, store, payload = catalog
    other = client.post("/api/sellers", json={"name": "Other", "email": "other@example.com"}).json()
    payload["seller_id"] = other["id"]
    assert client.post("/api/products", json=payload).status_code == 422
    assert client.get("/api/products").json() == []
    assert client.put(f"/api/stores/{store['id']}", json={"seller_id": other["id"], "name": "Moved", "address": "Address"}).status_code == 422

def test_inventory_crud_and_duplicate(client, catalog):
    product = client.post("/api/products", json=catalog[2]).json()
    inventory = client.get("/api/inventory").json()[0]
    payload = {"variant_id": product["variants"][0]["id"], "store_id": catalog[1]["id"], "quantity": 2}
    assert client.post("/api/inventory", json=payload).status_code == 409
    assert client.put(f"/api/inventory/{inventory['id']}", json={"quantity": -1}).status_code == 422
    assert client.delete(f"/api/inventory/{inventory['id']}").status_code == 204
    created = client.post("/api/inventory", json=payload)
    assert created.status_code == 201
    assert client.get(f"/api/inventory/{created.json()['id']}").json()["quantity"] == 2
    payload["variant_id"] = 99999
    assert client.post("/api/inventory", json=payload).status_code == 404

def test_seller_store_updates_and_email_uniqueness(client, catalog):
    seller, store, _ = catalog
    assert client.post("/api/sellers", json={"name": "Duplicate", "email": "STUDIO@example.com"}).status_code == 409
    assert client.put(f"/api/sellers/{seller['id']}", json={"name": "Renamed", "email": "new@example.com"}).json()["name"] == "Renamed"
    assert client.put(f"/api/stores/{store['id']}", json={"seller_id": seller["id"], "name": "Renamed", "address": "New address"}).status_code == 200
    assert client.get(f"/api/sellers/{seller['id']}").status_code == 200
    assert client.get(f"/api/stores/{store['id']}").status_code == 200
    assert client.get("/api/products?limit=201").status_code == 422

def test_variant_update(client, catalog):
    product = client.post("/api/products", json=catalog[2]).json()
    variant = product["variants"][0]
    payload = {key: variant[key] for key in ["sku", "size", "color", "mrp", "selling_price"]}
    payload["selling_price"] = "899.00"
    assert client.put(f"/api/products/{product['id']}/variants/{variant['id']}", json=payload).json()["selling_price"] == "899.00"
    assert client.put(f"/api/products/999/variants/{variant['id']}", json=payload).status_code == 404

def test_cors_and_deferred_protocol_routes(client):
    response = client.options("/api/products", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    response = client.options("/api/products", headers={"Origin": "https://untrusted.example", "Access-Control-Request-Method": "POST"})
    assert response.status_code == 400
    for path in ["/track"]:
        assert client.post(path, json={}).status_code == 404
