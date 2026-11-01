"""Catalog lifecycle state, checkout intents and confirmed ONDC orders."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("ondc_discovery_messages", sa.Column("callback_headers", sa.JSON, nullable=False,
                                                        server_default=sa.text("'{}'")))
    op.create_table("ondc_catalog_publication_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.Integer, nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("changed_at", sa.Float, nullable=False),
        sa.Column("published_at", sa.Float, nullable=True),
        sa.Column("rejection_code", sa.String(30), nullable=True),
        sa.Column("rejection_message", sa.String(500), nullable=True),
        sa.UniqueConstraint("entity_type", "entity_id"))
    op.create_table("ondc_checkout_intents",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("transaction_id", sa.String(255), nullable=False, unique=True),
        sa.Column("bap_id", sa.String(254), nullable=False),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="selected"),
        sa.Column("selection", sa.JSON, nullable=False),
        sa.Column("quote", sa.JSON, nullable=False),
        sa.Column("checkout", sa.JSON, nullable=True),
        sa.Column("expires_at", sa.Float, nullable=False))
    op.create_index("ix_ondc_checkout_intents_expires_at", "ondc_checkout_intents", ["expires_at"])
    op.create_table("ondc_orders",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("transaction_id", sa.String(255), nullable=False, unique=True),
        sa.Column("checkout_id", sa.Integer, sa.ForeignKey("ondc_checkout_intents.id"), nullable=False, unique=True),
        sa.Column("bap_id", sa.String(254), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="INR"),
        sa.Column("fulfillment", sa.JSON, nullable=False),
        sa.Column("payment", sa.JSON, nullable=False),
        sa.Column("billing", sa.JSON, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False),
        sa.Column("updated_at", sa.Float, nullable=False))
    op.create_table("ondc_order_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.String(255), sa.ForeignKey("ondc_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.String(255), nullable=False),
        sa.Column("variant_id", sa.Integer, sa.ForeignKey("product_variants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint("order_id", "item_id"))
    op.create_index("ix_ondc_order_items_order_id", "ondc_order_items", ["order_id"])

def downgrade():
    for table in ["ondc_order_items", "ondc_orders", "ondc_checkout_intents", "ondc_catalog_publication_state"]:
        op.drop_table(table)
    op.drop_column("ondc_discovery_messages", "callback_headers")
