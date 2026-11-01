
"""Execute Alembic operations and prove existing rows survive upgrade/downgrade."""
import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

def load(name):
    path = Path(__file__).parents[1] / "alembic" / "versions" / name
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

@pytest.mark.parametrize("cycle", [False, True])
def test_migration_preserves_existing_rows(tmp_path, cycle):
    engine = sa.create_engine("sqlite:///" + str(tmp_path / "migration.db"))
    with engine.begin() as conn:
        initial = load("0001_initial.py")
        added = load("0002_ondc_publication_discovery.py")
        unique = load("0003_ondc_provider_uniqueness.py")
        orders = load("0004_ondc_catalog_orders.py")
        post_order = load("0005_ondc_post_order_sync.py")
        operations = Operations(MigrationContext.configure(conn))
        initial.op = added.op = unique.op = orders.op = post_order.op = operations
        initial.upgrade()
        conn.execute(sa.text("INSERT INTO sellers (id,name,email) VALUES (1,'SR Fashions','local@example.com')"))
        conn.execute(sa.text("INSERT INTO stores (id,seller_id,name,address) VALUES (1,1,'Main Store','Bengaluru')"))
        added.upgrade()
        unique.upgrade()
        orders.upgrade()
        post_order.upgrade()
        tables = sa.inspect(conn).get_table_names()
        assert all(t in tables for t in ["ondc_seller_publication", "ondc_store_publication",
                                        "ondc_product_publication", "ondc_discovery_messages"])
        assert all(t in tables for t in ["ondc_catalog_publication_state", "ondc_checkout_intents",
                                         "ondc_orders", "ondc_order_items"])
        assert all(t in tables for t in ["ondc_order_state_events", "ondc_financial_events",
            "ondc_return_requests", "ondc_catalog_subscriptions", "ondc_catalog_publication_jobs"])
        assert conn.scalar(sa.text("SELECT COUNT(*) FROM sellers")) == 1
        assert conn.scalar(sa.text("SELECT COUNT(*) FROM ondc_seller_publication")) == 0
        conn.execute(sa.text("INSERT INTO ondc_seller_publication (seller_id,data) VALUES (1,'{}')"))
        assert not conn.scalar(sa.text("SELECT enabled FROM ondc_seller_publication"))
        if cycle:
            post_order.downgrade()
            orders.downgrade()
            unique.downgrade()
            added.downgrade()
            assert conn.scalar(sa.text("SELECT name FROM sellers")) == "SR Fashions"
            assert "ondc_discovery_messages" not in sa.inspect(conn).get_table_names()
            added.upgrade()
            unique.upgrade()
            orders.upgrade()
            post_order.upgrade()
            assert conn.scalar(sa.text("SELECT COUNT(*) FROM stores")) == 1
    engine.dispose()


def test_postgresql_migrations_and_replay_workers():
    """Local PostgreSQL only; isolate every operation in a generated temporary schema."""
    import os
    import re
    import uuid
    import time
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    from sqlalchemy.exc import IntegrityError
    from app.database import get_engine
    from app.ondc.models import DiscoveryMessage
    from app.models import Inventory
    if os.getenv("ONDC_TEST_POSTGRES") != "1":
        pytest.skip("Set ONDC_TEST_POSTGRES=1 to test local PostgreSQL")
    engine = get_engine()
    schema = "ondc_test_" + uuid.uuid4().hex
    assert re.fullmatch(r"ondc_test_[a-f0-9]{32}", schema)
    with engine.begin() as conn:
        conn.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
    try:
        with engine.begin() as conn:
            conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert conn.scalar(sa.text("SELECT current_schema()")) == schema
            operations = Operations(MigrationContext.configure(conn))
            migrations = [load(name) for name in ["0001_initial.py", "0002_ondc_publication_discovery.py",
                                                  "0003_ondc_provider_uniqueness.py", "0004_ondc_catalog_orders.py"]]
            migrations.append(load("0005_ondc_post_order_sync.py"))
            for migration in migrations:
                migration.op = operations
            migrations[0].upgrade()
            conn.execute(sa.text("INSERT INTO sellers (id,name,email) VALUES (1,'SR Fashions','migration@example.com')"))
            conn.execute(sa.text("INSERT INTO stores (id,seller_id,name,address) VALUES (1,1,'Main Store','Bengaluru')"))
            migrations[1].upgrade()
            migrations[2].upgrade()
            migrations[3].upgrade()
            migrations[4].upgrade()
            assert conn.scalar(sa.text("SELECT COUNT(*) FROM sellers")) == 1
            assert conn.scalar(sa.text("SELECT COUNT(*) FROM stores")) == 1
            conn.execute(sa.text("INSERT INTO ondc_seller_publication (seller_id,data) VALUES (1,'{}')"))
            assert conn.scalar(sa.text("SELECT enabled FROM ondc_seller_publication")) is False
            conn.execute(sa.text("INSERT INTO products (id,seller_id,name,brand,description,category) VALUES (1,1,'Shirt','SR','','Shirts')"))
            conn.execute(sa.text("INSERT INTO product_variants (id,product_id,sku,size,color,mrp,selling_price) VALUES (1,1,'LAST-S','S','Black',100,90)"))
            conn.execute(sa.text("INSERT INTO inventory (id,variant_id,store_id,quantity) VALUES (1,1,1,1)"))
        translated = engine.execution_options(schema_translate_map={None: schema})
        def accept_worker(_):
            with Session(translated) as db:
                record = DiscoveryMessage(sender="buyer.example.com", domain="ONDC:RET12", action="search",
                    transaction_id="PG-T1", message_id="PG-M1", body_hash="0"*128, request={},
                    callback={}, destination="http://127.0.0.1/on_search", retain_until=time.time()+86400)
                db.add(record)
                try:
                    db.commit()
                    return record.id
                except IntegrityError:
                    db.rollback()
                    return db.scalar(sa.select(DiscoveryMessage.id).where(DiscoveryMessage.message_id == "PG-M1"))
        with ThreadPoolExecutor(max_workers=2) as pool:
            identities = list(pool.map(accept_worker, range(2)))
        assert identities[0] == identities[1]
        def claim_worker(_):
            with Session(translated) as db:
                claimed = db.execute(sa.update(DiscoveryMessage).where(
                    DiscoveryMessage.id == identities[0], DiscoveryMessage.lease_until < time.time()).values(
                        status="sending", lease_until=time.time()+60, attempts=DiscoveryMessage.attempts+1))
                db.commit()
                return claimed.rowcount
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(claim_worker, range(2))) == [0, 1]
        def reserve_last_item(_):
            with Session(translated) as db:
                row = db.scalar(sa.select(Inventory).where(Inventory.id == 1).with_for_update())
                if row.quantity < 1:
                    db.rollback()
                    return False
                row.quantity -= 1
                db.commit()
                return True
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(reserve_last_item, range(2))) == [False, True]
        with Session(translated) as db:
            assert db.get(Inventory, 1).quantity == 0
        with engine.begin() as conn:
            conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert conn.scalar(sa.text("SELECT current_schema()")) == schema
            operations = Operations(MigrationContext.configure(conn))
            for migration in migrations[1:]:
                migration.op = operations
            migrations[4].downgrade()
            migrations[3].downgrade()
            migrations[2].downgrade()
            migrations[1].downgrade()
            assert conn.scalar(sa.text("SELECT name FROM sellers WHERE id=1")) == "SR Fashions"
            migrations[1].upgrade()
            migrations[2].upgrade()
            migrations[3].upgrade()
            migrations[4].upgrade()
            assert conn.scalar(sa.text("SELECT COUNT(*) FROM stores")) == 1
    finally:
        with engine.begin() as conn:
            # Only the exact, generated, task-owned schema is removed.
            assert re.fullmatch(r"ondc_test_[a-f0-9]{32}", schema)
            conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
