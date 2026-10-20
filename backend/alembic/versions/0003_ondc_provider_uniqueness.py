
"""Prevent concurrent administration from enabling multiple ISN providers."""
from alembic import op
import sqlalchemy as sa
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("uq_ondc_one_enabled_provider", "ondc_seller_publication", ["enabled"], unique=True,
                    postgresql_where=sa.text("enabled = true"), sqlite_where=sa.text("enabled = 1"))

def downgrade():
    op.drop_index("uq_ondc_one_enabled_provider", table_name="ondc_seller_publication")
