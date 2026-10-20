
"""Publication extensions and durable inbound/outbound discovery state."""
from sqlalchemy import JSON, Index, text, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class SellerPublication(Base):
    __tablename__ = "ondc_seller_publication"
    __table_args__ = (Index("uq_ondc_one_enabled_provider", "enabled", unique=True,
                           postgresql_where=text("enabled = true"), sqlite_where=text("enabled = 1")),)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(default=False)

class StorePublicationRow(Base):
    __tablename__ = "ondc_store_publication"
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)

class ProductPublicationRow(Base):
    __tablename__ = "ondc_product_publication"
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    data: Mapped[dict] = mapped_column(JSON)

class DiscoveryMessage(Base):
    __tablename__ = "ondc_discovery_messages"
    __table_args__ = (UniqueConstraint("sender", "domain", "action", "transaction_id", "message_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    sender: Mapped[str] = mapped_column(String(254))
    domain: Mapped[str] = mapped_column(String(50))
    action: Mapped[str] = mapped_column(String(30))
    transaction_id: Mapped[str] = mapped_column(String(255))
    message_id: Mapped[str] = mapped_column(String(255))
    body_hash: Mapped[str] = mapped_column(String(128))
    request: Mapped[dict] = mapped_column(JSON)
    callback: Mapped[dict] = mapped_column(JSON)
    destination: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    retain_until: Mapped[float] = mapped_column(Float, index=True)
    error: Mapped[str | None] = mapped_column(String(50), nullable=True)
