from datetime import datetime
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Id = Annotated[int, Field(gt=0)]
Stock = Annotated[int, Field(ge=0, le=2147483647, strict=True)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Output(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    updated_at: datetime


class SellerWrite(Input):
    name: Name
    email: Annotated[str, StringConstraints(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()


class SellerRead(Output):
    name: str
    email: str


class StoreWrite(Input):
    seller_id: Id
    name: Name
    address: Annotated[str, StringConstraints(min_length=1, max_length=500)]


class StoreRead(Output):
    seller_id: int
    name: str
    address: str


class VariantWrite(Input):
    sku: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    size: Annotated[str, StringConstraints(min_length=1, max_length=50)]
    color: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    mrp: Money
    selling_price: Money

    @model_validator(mode="after")
    def valid_price(self):
        if self.selling_price > self.mrp:
            raise ValueError("Selling price must not exceed MRP")
        return self


class VariantCreate(VariantWrite):
    initial_stock: Stock = 0
    store_id: Id | None = None

    @model_validator(mode="after")
    def stock_store(self):
        if self.initial_stock and self.store_id is None:
            raise ValueError("store_id is required for initial stock")
        return self


class VariantRead(Output):
    product_id: int
    sku: str
    size: str
    color: str
    mrp: Decimal
    selling_price: Decimal


class ProductWrite(Input):
    name: Name
    brand: Name
    description: Annotated[str, StringConstraints(max_length=10000)] = ""
    category: Name  # Internal free-text label, NOT an ONDC taxonomy code.


class ProductCreate(ProductWrite):
    seller_id: Id
    variants: list[VariantCreate] = Field(min_length=1, max_length=100)


class ProductRead(Output):
    seller_id: int
    name: str
    brand: str
    description: str
    category: str
    variants: list[VariantRead]


class InventoryWrite(Input):
    variant_id: Id
    store_id: Id
    quantity: Stock


class InventoryUpdate(Input):
    quantity: Stock


class InventoryRead(Output):
    variant_id: int
    store_id: int
    quantity: int
