"""Strict Retail B2C 1.2.5 subset for the supported RET12 purchase flow."""
from decimal import Decimal
from typing import Literal
from pydantic import Field, field_validator, model_validator
from app.ondc.schemas.base import HttpUrl, Text, Timestamp, WireModel
from app.ondc.schemas.context import Context

MoneyText = str

class Count(WireModel):
    count: int = Field(ge=1, le=2147483647, strict=True)

class ProviderLocation(WireModel):
    id: Text

class ProviderRef(WireModel):
    id: Text
    locations: list[ProviderLocation] = Field(min_length=1, max_length=1)

class OrderItem(WireModel):
    id: Text
    quantity: Count
    location_id: Text | None = None
    fulfillment_id: Text | None = None

class Address(WireModel):
    name: Text | None = None
    building: Text | None = None
    locality: Text | None = None
    city: Text | None = None
    state: Text | None = None
    country: Literal["IND"] | None = None
    area_code: Text

class Location(WireModel):
    gps: Text | None = None
    address: Address

class Contact(WireModel):
    phone: Text
    email: Text | None = None

class Person(WireModel):
    name: Text

class End(WireModel):
    location: Location
    contact: Contact | None = None
    person: Person | None = None

class SelectFulfillment(WireModel):
    end: End

class SelectedFulfillment(WireModel):
    id: Text
    type: Literal["Delivery"]
    end: End

class Billing(WireModel):
    address: Address
    phone: Text
    name: Text
    email: Text | None = None
    created_at: Timestamp
    updated_at: Timestamp

class SelectOrder(WireModel):
    provider: ProviderRef
    items: list[OrderItem] = Field(min_length=1, max_length=100)
    fulfillments: list[SelectFulfillment] = Field(min_length=1, max_length=1)

class InitOrder(WireModel):
    provider: ProviderRef
    items: list[OrderItem] = Field(min_length=1, max_length=100)
    billing: Billing
    fulfillments: list[SelectedFulfillment] = Field(min_length=1, max_length=1)

class PaymentParams(WireModel):
    amount: MoneyText
    currency: Literal["INR"]
    transaction_id: Text | None = None

class Payment(WireModel):
    params: PaymentParams
    status: Literal["PAID", "NOT-PAID"]
    type: Literal["ON-ORDER", "ON-FULFILLMENT", "POST-FULFILLMENT"]
    collected_by: Literal["BAP", "BPP"]
    buyer_app_finder_fee_type: Literal["amount", "percent"] | None = Field(default=None, alias="@ondc/org/buyer_app_finder_fee_type")
    buyer_app_finder_fee_amount: MoneyText | None = Field(default=None, alias="@ondc/org/buyer_app_finder_fee_amount")

class QuotePrice(WireModel):
    currency: Literal["INR"]
    value: MoneyText

class ConfirmQuote(WireModel):
    price: QuotePrice
    breakup: list[dict]
    ttl: Text

class ConfirmOrder(WireModel):
    id: Text
    state: Literal["Created"]
    provider: ProviderRef
    items: list[OrderItem] = Field(min_length=1, max_length=100)
    billing: Billing
    fulfillments: list[SelectedFulfillment] = Field(min_length=1, max_length=1)
    quote: ConfirmQuote
    payment: Payment
    created_at: Timestamp
    updated_at: Timestamp
    tags: list[dict] | None = None

class SelectMessage(WireModel): order: SelectOrder
class InitMessage(WireModel): order: InitOrder
class ConfirmMessage(WireModel): order: ConfirmOrder

class SelectRequest(WireModel):
    context: Context
    message: SelectMessage

    @model_validator(mode="after")
    def action(self):
        if self.context.action != "select": raise ValueError("Expected select action")
        return self

class InitRequest(WireModel):
    context: Context
    message: InitMessage

    @model_validator(mode="after")
    def action(self):
        if self.context.action != "init": raise ValueError("Expected init action")
        return self

class ConfirmRequest(WireModel):
    context: Context
    message: ConfirmMessage

    @model_validator(mode="after")
    def action(self):
        if self.context.action != "confirm": raise ValueError("Expected confirm action")
        return self

def money(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except Exception:
        raise ValueError("Invalid monetary value") from None
    if parsed < 0 or parsed.as_tuple().exponent < -2:
        raise ValueError("Invalid monetary value")
    return parsed
