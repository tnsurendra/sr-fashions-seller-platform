"""Post-order state/audit/accounting and durable catalog scheduling."""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

def upgrade():
    for name, column in [
        ("internal_state", sa.Column("internal_state", sa.String(40), nullable=False, server_default="accepted")),
        ("fulfillment_state", sa.Column("fulfillment_state", sa.String(40), nullable=False, server_default="Pending")),
        ("version", sa.Column("version", sa.Integer, nullable=False, server_default="1")),
        ("inventory_restored", sa.Column("inventory_restored", sa.Boolean, nullable=False, server_default=sa.false())),
        ("cancelled_at", sa.Column("cancelled_at", sa.Float, nullable=True))]:
        op.add_column("ondc_orders", column)
    op.create_table("ondc_order_state_events",
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("order_id", sa.String(255), sa.ForeignKey("ondc_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False), sa.Column("from_state", sa.String(40), nullable=False),
        sa.Column("to_state", sa.String(40), nullable=False), sa.Column("fulfillment_state", sa.String(40), nullable=False),
        sa.Column("actor", sa.String(30), nullable=False), sa.Column("source", sa.String(30), nullable=False),
        sa.Column("occurred_at", sa.Float, nullable=False), sa.Column("detail", sa.JSON, nullable=False),
        sa.UniqueConstraint("order_id", "idempotency_key"))
    op.create_index("ix_ondc_order_state_events_order_id", "ondc_order_state_events", ["order_id"])
    op.create_table("ondc_financial_events",
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("order_id", sa.String(255), sa.ForeignKey("ondc_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False), sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False), sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("amount", sa.Numeric(12,2), nullable=False), sa.Column("transaction_reference", sa.String(255), nullable=True),
        sa.Column("occurred_at", sa.Float, nullable=False), sa.Column("detail", sa.JSON, nullable=False),
        sa.UniqueConstraint("order_id", "idempotency_key"))
    op.create_index("ix_ondc_financial_events_order_id", "ondc_financial_events", ["order_id"])
    op.create_table("ondc_return_requests",
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("order_id", sa.String(255), sa.ForeignKey("ondc_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.String(255), nullable=False), sa.Column("item_id", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False), sa.Column("reason_id", sa.String(20), nullable=False),
        sa.Column("reason_description", sa.String(1000), nullable=True), sa.Column("state", sa.String(40), nullable=False),
        sa.Column("requested_at", sa.Float, nullable=False), sa.Column("decided_at", sa.Float, nullable=True),
        sa.UniqueConstraint("order_id", "request_id"))
    op.create_index("ix_ondc_return_requests_order_id", "ondc_return_requests", ["order_id"])
    op.create_table("ondc_catalog_subscriptions",
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("bap_id", sa.String(254), nullable=False),
        sa.Column("bap_uri", sa.Text, nullable=False), sa.Column("transaction_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("interval_seconds", sa.Integer, nullable=False),
        sa.Column("cursor_at", sa.Float, nullable=False), sa.Column("next_run_at", sa.Float, nullable=False),
        sa.Column("created_at", sa.Float, nullable=False), sa.Column("updated_at", sa.Float, nullable=False),
        sa.UniqueConstraint("bap_id", "transaction_id"))
    op.create_index("ix_ondc_catalog_subscriptions_next_run_at", "ondc_catalog_subscriptions", ["next_run_at"])
    op.create_table("ondc_catalog_publication_jobs",
        sa.Column("id", sa.Integer, primary_key=True), sa.Column("subscription_id", sa.Integer, sa.ForeignKey("ondc_catalog_subscriptions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("window_start", sa.Float, nullable=False), sa.Column("window_end", sa.Float, nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lease_until", sa.Float, nullable=False, server_default="0"), sa.Column("next_attempt_at", sa.Float, nullable=False),
        sa.Column("error", sa.String(50), nullable=True), sa.Column("created_at", sa.Float, nullable=False),
        sa.UniqueConstraint("subscription_id", "window_start", "window_end"))
    op.create_index("ix_ondc_catalog_publication_jobs_subscription_id", "ondc_catalog_publication_jobs", ["subscription_id"])

def downgrade():
    for table in ["ondc_catalog_publication_jobs", "ondc_catalog_subscriptions", "ondc_return_requests", "ondc_financial_events", "ondc_order_state_events"]:
        op.drop_table(table)
    for name in ["cancelled_at", "inventory_restored", "version", "fulfillment_state", "internal_state"]:
        op.drop_column("ondc_orders", name)
