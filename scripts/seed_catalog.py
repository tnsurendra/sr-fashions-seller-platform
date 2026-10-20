"""Create reusable SR Fashions catalog through the running API; preserve existing records."""
import os
import httpx

with httpx.Client(base_url=os.getenv("API_BASE_URL", "http://127.0.0.1:8000"), timeout=15) as client:
    def request(method, path, **kwargs):
        response = client.request(method, path, **kwargs)
        response.raise_for_status()
        return response.json()

    def all_rows(path):
        rows = []
        while True:
            page = request("GET", path, params={"limit": 200, "offset": len(rows)})
            rows.extend(page)
            if len(page) < 200:
                return rows

    seller = next((row for row in all_rows("/api/sellers") if row["email"] == "sales@sr-fashions.example.com"), None)
    if seller is None:
        seller = request("POST", "/api/sellers", json={"name": "SR Fashions", "email": "sales@sr-fashions.example.com"})
    store = next((row for row in all_rows("/api/stores") if row["seller_id"] == seller["id"] and row["name"] == "SR Fashions Main Store"), None)
    if store is None:
        store = request("POST", "/api/stores", json={"seller_id": seller["id"], "name": "SR Fashions Main Store", "address": "SR Fashions Main Store - address pending"})
    samples = [
        ("SR Essentials Regular-Fit Cotton Shirt", "SR Essentials", "Shirts", "Cotton shirt with a regular fit.", [("SR-SHIRT-BLUE-M", "M", "Blue", "1499.00", "1199.00", 20), ("SR-SHIRT-BLUE-L", "L", "Blue", "1499.00", "1199.00", 12)]),
        ("SR Denim Straight-Fit Jeans", "SR Denim", "Jeans", "Everyday straight-fit denim jeans.", [("SR-JEANS-INDIGO-32", "32", "Indigo", "2499.00", "1999.00", 15)]),
        ("SR Studio Printed Cotton Kurta", "SR Studio", "Kurtas", "Printed cotton kurta for everyday wear.", [("SR-KURTA-GREEN-M", "M", "Green", "1799.00", "1399.00", 8)]),
        ("SR Essentials Cotton Crew-Neck T-Shirt", "SR Essentials", "T-Shirts", "Soft cotton crew-neck T-shirt.", [("SR-TEE-BLACK-M", "M", "Black", "799.00", "599.00", 30)]),
        ("SR Active Fleece Zip-Up Hoodie", "SR Active", "Hoodies", "Fleece hoodie with a full-length zip.", [("SR-HOODIE-GREY-L", "L", "Grey", "2299.00", "1799.00", 0)]),
    ]
    existing = {variant["sku"] for product in all_rows("/api/products") for variant in product["variants"]}
    for name, brand, category, description, variants in samples:
        if any(variant[0] in existing for variant in variants):
            print(f"SKIP existing catalog SKU: {name}")
            continue
        product = request("POST", "/api/products", json={"seller_id": seller["id"], "name": name, "brand": brand, "category": category, "description": description,
            "variants": [{"sku": sku, "size": size, "color": color, "mrp": mrp, "selling_price": price, "store_id": store["id"], "initial_stock": stock}
                         for sku, size, color, mrp, price, stock in variants]})
        print(f"CREATED product {product['id']}: {name}")
    print(f"SR Fashions seller ID: {seller['id']}; store ID: {store['id']}")
