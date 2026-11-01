
"""Publication extensions and durable inbound/outbound discovery state."""
from sqlalchemy import JSON, Index, text, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
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
    callback_headers: Mapped[dict] = mapped_column(JSON, default=dict)
    destination: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    retain_until: Mapped[float] = mapped_column(Float, index=True)
    error: Mapped[str | None] = mapped_column(String(50), nullable=True)

class CatalogPublicationState(Base):
    __tablename__ = "ondc_catalog_publication_state"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(20))
    entity_id: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    changed_at: Mapped[float] = mapped_column(Float)
    published_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    rejection_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    rejection_message: Mapped[str | None] = mapped_column(String(500), nullable=True)

class CheckoutIntent(Base):
    __tablename__ = "ondc_checkout_intents"
    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(255), unique=True)
    bap_id: Mapped[str] = mapped_column(String(254))
    provider_id: Mapped[str] = mapped_column(String(255))
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"))
    state: Mapped[str] = mapped_column(String(20), default="selected")
    selection: Mapped[dict] = mapped_column(JSON)
    quote: Mapped[dict] = mapped_column(JSON)
    checkout: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expires_at: Mapped[float] = mapped_column(Float, index=True)

class ONDCOrder(Base):
    __tablename__ = "ondc_orders"
    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(String(255), unique=True)
    checkout_id: Mapped[int] = mapped_column(ForeignKey("ondc_checkout_intents.id"), unique=True)
    bap_id: Mapped[str] = mapped_column(String(254))
    state: Mapped[str] = mapped_column(String(30))
    amount: Mapped[object] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    fulfillment: Mapped[dict] = mapped_column(JSON)
    payment: Mapped[dict] = mapped_column(JSON)
    billing: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)
    internal_state: Mapped[str] = mapped_column(String(40), default="accepted")
    fulfillment_state: Mapped[str] = mapped_column(String(40), default="Pending")
    version: Mapped[int] = mapped_column(Integer, default=1)
    inventory_restored: Mapped[bool] = mapped_column(default=False)
    cancelled_at: Mapped[float | None] = mapped_column(Float, nullable=True)

class ONDCOrderItem(Base):
    __tablename__ = "ondc_order_items"
    __table_args__ = (UniqueConstraint("order_id", "item_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("ondc_orders.id", ondelete="CASCADE"), index=True)
    item_id: Mapped[str] = mapped_column(String(255))
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id", ondelete="RESTRICT"))
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[object] = mapped_column(Numeric(12, 2))
    total_price: Mapped[object] = mapped_column(Numeric(12, 2))

class OrderStateEvent(Base):
    __tablename__ = "ondc_order_state_events"
    __table_args__ = (UniqueConstraint("order_id", "idempotency_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("ondc_orders.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    from_state: Mapped[str] = mapped_column(String(40))
    to_state: Mapped[str] = mapped_column(String(40))
    fulfillment_state: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(30))
    source: Mapped[str] = mapped_column(String(30))
    occurred_at: Mapped[float] = mapped_column(Float)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)

class FinancialEvent(Base):
    __tablename__ = "ondc_financial_events"
    __table_args__ = (UniqueConstraint("order_id", "idempotency_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("ondc_orders.id", ondelete="CASCADE"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    event_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[object] = mapped_column(Numeric(12, 2))
    transaction_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[float] = mapped_column(Float)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)

class ReturnRequest(Base):
    __tablename__ = "ondc_return_requests"
    __table_args__ = (UniqueConstraint("order_id", "request_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("ondc_orders.id", ondelete="CASCADE"), index=True)
    request_id: Mapped[str] = mapped_column(String(255))
    item_id: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    reason_id: Mapped[str] = mapped_column(String(20))
    reason_description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    state: Mapped[str] = mapped_column(String(40))
    requested_at: Mapped[float] = mapped_column(Float)
    decided_at: Mapped[float | None] = mapped_column(Float, nullable=True)

class CatalogSubscription(Base):
    __tablename__ = "ondc_catalog_subscriptions"
    __table_args__ = (UniqueConstraint("bap_id", "transaction_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    bap_id: Mapped[str] = mapped_column(String(254))
    bap_uri: Mapped[str] = mapped_column(Text)
    transaction_id: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))
    interval_seconds: Mapped[int] = mapped_column(Integer)
    cursor_at: Mapped[float] = mapped_column(Float)
    next_run_at: Mapped[float] = mapped_column(Float, index=True)
    created_at: Mapped[float] = mapped_column(Float)
    updated_at: Mapped[float] = mapped_column(Float)

class CatalogPublicationJob(Base):
    __tablename__ = "ondc_catalog_publication_jobs"
    __table_args__ = (UniqueConstraint("subscription_id", "window_start", "window_end"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("ondc_catalog_subscriptions.id", ondelete="CASCADE"), index=True)
    window_start: Mapped[float] = mapped_column(Float)
    window_end: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    next_attempt_at: Mapped[float] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[float] = mapped_column(Float)
