import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app

@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    def override_db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()

@pytest.fixture
def catalog(client):
    seller = client.post("/api/sellers", json={"name": "Studio", "email": "studio@example.com"}).json()
    store = client.post("/api/stores", json={"seller_id": seller["id"], "name": "Main", "address": "Local shop"}).json()
    payload = {"seller_id": seller["id"], "name": "Shirt", "brand": "Studio", "description": "Cotton shirt", "category": "Shirts",
        "variants": [{"sku": "SHIRT-BLUE-M", "size": "M", "color": "Blue", "mrp": "1200.00", "selling_price": "999.00",
                      "store_id": store["id"], "initial_stock": 5}]}
    return seller, store, payload
