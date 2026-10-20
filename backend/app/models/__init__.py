from datetime import datetime
from decimal import Decimal
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Seller(TimestampMixin, Base):
    __tablename__ = "sellers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(254), unique=True)
    stores: Mapped[list["Store"]] = relationship(back_populates="seller", passive_deletes="all")
    products: Mapped[list["Product"]] = relationship(back_populates="seller", passive_deletes="all")


class Store(TimestampMixin, Base):
    __tablename__ = "stores"
    __table_args__ = (UniqueConstraint("seller_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str] = mapped_column(String(500))
    seller: Mapped[Seller] = relationship(back_populates="stores")
    inventory: Mapped[list["Inventory"]] = relationship(back_populates="store", passive_deletes="all")


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey("sellers.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(200))
    seller: Mapped[Seller] = relationship(back_populates="products")
    variants: Mapped[list["ProductVariant"]] = relationship(back_populates="product", cascade="all, delete-orphan", passive_deletes=True)


class ProductVariant(TimestampMixin, Base):
    __tablename__ = "product_variants"
    __table_args__ = (
        CheckConstraint("mrp >= 0", name="mrp_nonnegative"),
        CheckConstraint("selling_price >= 0 AND selling_price <= mrp", name="valid_selling_price"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(100), unique=True)
    size: Mapped[str] = mapped_column(String(50))
    color: Mapped[str] = mapped_column(String(100))
    mrp: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    selling_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    product: Mapped[Product] = relationship(back_populates="variants")
    inventory: Mapped[list["Inventory"]] = relationship(back_populates="variant", cascade="all, delete-orphan", passive_deletes=True)


class Inventory(TimestampMixin, Base):
    __tablename__ = "inventory"
    __table_args__ = (
        UniqueConstraint("variant_id", "store_id"),
        CheckConstraint("quantity >= 0 AND quantity <= 2147483647", name="valid_quantity"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    variant_id: Mapped[int] = mapped_column(ForeignKey("product_variants.id", ondelete="CASCADE"), index=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    variant: Mapped[ProductVariant] = relationship(back_populates="inventory")
    store: Mapped[Store] = relationship(back_populates="inventory")
