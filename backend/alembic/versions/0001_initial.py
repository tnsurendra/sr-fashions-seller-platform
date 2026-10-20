"""Initial internal retailer data model. No ONDC protocol tables."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def timestamps():
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade():
    op.create_table("sellers", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("email", sa.String(254), nullable=False),
        sa.UniqueConstraint("email"), *timestamps())
    op.create_table("stores", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("seller_id", sa.Integer, sa.ForeignKey("sellers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("address", sa.String(500), nullable=False),
        sa.UniqueConstraint("seller_id", "name"), *timestamps())
    op.create_table("products", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("seller_id", sa.Integer, sa.ForeignKey("sellers.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False), sa.Column("brand", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False), sa.Column("category", sa.String(200), nullable=False), *timestamps())
    op.create_table("product_variants", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False), sa.Column("size", sa.String(50), nullable=False),
        sa.Column("color", sa.String(100), nullable=False), sa.Column("mrp", sa.Numeric(12, 2), nullable=False),
        sa.Column("selling_price", sa.Numeric(12, 2), nullable=False), sa.UniqueConstraint("sku"),
        sa.CheckConstraint("mrp >= 0", name="mrp_nonnegative"),
        sa.CheckConstraint("selling_price >= 0 AND selling_price <= mrp", name="valid_selling_price"), *timestamps())
    op.create_table("inventory", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("variant_id", sa.Integer, sa.ForeignKey("product_variants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("store_id", sa.Integer, sa.ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False), sa.UniqueConstraint("variant_id", "store_id"),
        sa.CheckConstraint("quantity >= 0 AND quantity <= 2147483647", name="valid_quantity"), *timestamps())
    for table, columns in {"stores": ["seller_id"], "products": ["seller_id"],
            "product_variants": ["product_id"], "inventory": ["variant_id", "store_id"]}.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    for table in ["inventory", "product_variants", "products", "stores", "sellers"]:
        op.drop_table(table)
