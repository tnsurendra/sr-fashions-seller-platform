
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
        operations = Operations(MigrationContext.configure(conn))
        initial.op = added.op = unique.op = operations
        initial.upgrade()
        conn.execute(sa.text("INSERT INTO sellers (id,name,email) VALUES (1,'SR Fashions','local@example.com')"))
        conn.execute(sa.text("INSERT INTO stores (id,seller_id,name,address) VALUES (1,1,'Main Store','Bengaluru')"))
        added.upgrade()
        unique.upgrade()
        tables = sa.inspect(conn).get_table_names()
        assert all(t in tables for t in ["ondc_seller_publication", "ondc_store_publication",
                                        "ondc_product_publication", "ondc_discovery_messages"])
        assert conn.scalar(sa.text("SELECT COUNT(*) FROM sellers")) == 1
        assert conn.scalar(sa.text("SELECT COUNT(*) FROM ondc_seller_publication")) == 0
        conn.execute(sa.text("INSERT INTO ondc_seller_publication (seller_id,data) VALUES (1,'{}')"))
        assert not conn.scalar(sa.text("SELECT enabled FROM ondc_seller_publication"))
        if cycle:
            unique.downgrade()
            added.downgrade()
            assert conn.scalar(sa.text("SELECT name FROM sellers")) == "SR Fashions"
            assert "ondc_discovery_messages" not in sa.inspect(conn).get_table_names()
            added.upgrade()
            unique.upgrade()
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
                                                  "0003_ondc_provider_uniqueness.py"]]
            for migration in migrations:
                migration.op = operations
            migrations[0].upgrade()
            conn.execute(sa.text("INSERT INTO sellers (id,name,email) VALUES (1,'SR Fashions','migration@example.com')"))
            conn.execute(sa.text("INSERT INTO stores (id,seller_id,name,address) VALUES (1,1,'Main Store','Bengaluru')"))
            migrations[1].upgrade()
            migrations[2].upgrade()
            assert conn.scalar(sa.text("SELECT COUNT(*) FROM sellers")) == 1
            assert conn.scalar(sa.text("SELECT COUNT(*) FROM stores")) == 1
            conn.execute(sa.text("INSERT INTO ondc_seller_publication (seller_id,data) VALUES (1,'{}')"))
            assert conn.scalar(sa.text("SELECT enabled FROM ondc_seller_publication")) is False
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
        with engine.begin() as conn:
            conn.execute(sa.text(f'SET LOCAL search_path TO "{schema}"'))
            assert conn.scalar(sa.text("SELECT current_schema()")) == schema
            operations = Operations(MigrationContext.configure(conn))
            for migration in migrations[1:]:
                migration.op = operations
            migrations[2].downgrade()
            migrations[1].downgrade()
            assert conn.scalar(sa.text("SELECT name FROM sellers WHERE id=1")) == "SR Fashions"
            migrations[1].upgrade()
            migrations[2].upgrade()
            assert conn.scalar(sa.text("SELECT COUNT(*) FROM stores")) == 1
    finally:
        with engine.begin() as conn:
            # Only the exact, generated, task-owned schema is removed.
            assert re.fullmatch(r"ondc_test_[a-f0-9]{32}", schema)
            conn.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
