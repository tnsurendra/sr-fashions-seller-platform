
"""Add opt-in publication enrichment and durable discovery; existing rows untouched."""
from alembic import op
import sqlalchemy as sa
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

def upgrade():
    for table, column, parent in [
        ("ondc_seller_publication", "seller_id", "sellers"),
        ("ondc_store_publication", "store_id", "stores"),
        ("ondc_product_publication", "product_id", "products")]:
        columns = [sa.Column(column, sa.Integer, sa.ForeignKey(parent + ".id", ondelete="CASCADE"), primary_key=True),
                   sa.Column("data", sa.JSON, nullable=False)]
        if parent == "sellers":
            columns.append(sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.false()))
        op.create_table(table, *columns)
    op.create_table("ondc_discovery_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sender", sa.String(254), nullable=False),
        sa.Column("domain", sa.String(50), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("transaction_id", sa.String(255), nullable=False),
        sa.Column("message_id", sa.String(255), nullable=False),
        sa.Column("body_hash", sa.String(128), nullable=False),
        sa.Column("request", sa.JSON, nullable=False),
        sa.Column("callback", sa.JSON, nullable=False),
        sa.Column("destination", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lease_until", sa.Float, nullable=False, server_default="0"),
        sa.Column("retain_until", sa.Float, nullable=False),
        sa.Column("error", sa.String(50), nullable=True),
        sa.UniqueConstraint("sender", "domain", "action", "transaction_id", "message_id"))
    op.create_index("ix_ondc_discovery_messages_retain_until", "ondc_discovery_messages", ["retain_until"])

def downgrade():
    for table in ["ondc_discovery_messages", "ondc_product_publication", "ondc_store_publication", "ondc_seller_publication"]:
        op.drop_table(table)
