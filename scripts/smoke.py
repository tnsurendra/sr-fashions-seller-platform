"""Exercise the running PostgreSQL-backed API; remove only records created here."""
import os
from uuid import uuid4
import httpx

suffix = uuid4().hex
created = []
with httpx.Client(base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"), timeout=15) as client:
    def request(method, path, expected=200, **kwargs):
        response = client.request(method, path, **kwargs)
        assert response.status_code == expected, f"{method} {path}: {response.status_code} {response.text}"
        return response.json() if response.content else None
    try:
        assert request("GET", "/health") == {"status": "ok", "database": "ok"}
        seller = request("POST", "/api/sellers", 201, json={"name": "Smoke seller", "email": f"smoke-{suffix}@example.com"})
        created.append(f"/api/sellers/{seller['id']}")
        store = request("POST", "/api/stores", 201, json={"seller_id": seller["id"], "name": "Smoke store", "address": "Test location"})
        created.append(f"/api/stores/{store['id']}")
        payload = {"seller_id": seller["id"], "name": "Smoke shirt", "brand": "Test", "description": "Temporary verification record", "category": "Internal test category",
            "variants": [{"sku": suffix, "size": "M", "color": "Blue", "mrp": "100.00", "selling_price": "90.00", "store_id": store["id"], "initial_stock": 3}]}
        product = request("POST", "/api/products", 201, json=payload)
        created.append(f"/api/products/{product['id']}")
        request("GET", f"/api/products/{product['id']}")
        rows = request("GET", f"/api/inventory?store_id={store['id']}")
        assert len(rows) == 1 and rows[0]["quantity"] == 3
        updated = request("PUT", f"/api/inventory/{rows[0]['id']}", json={"quantity": 7})
        assert updated["quantity"] == 7
        request("POST", "/api/products", 409, json=payload)
        print("PASS: live health, product creation, inventory update, and duplicate-SKU rejection")
    finally:
        for path in reversed(created):
            request("DELETE", path, 204)
        print("Temporary smoke-test records removed")
