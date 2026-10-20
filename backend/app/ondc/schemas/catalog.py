"""Supported RET12 full catalog profile derived from the official 1.2.5 API contract.

Optional enhancements (offers, credentials, replacement terms, ratings) are not
fabricated. Unknown fields fail closed in this foundation's supported profile.
"""
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, StringConstraints, field_validator, model_validator
from app.ondc.schemas.base import Duration, HttpUrl, Text, Timestamp, WireModel
from app.ondc.schemas.context import Context
from app.ondc.schemas.tags import TagGroup
from app.ondc.catalog.taxonomy import category_definition, validate_attributes


class Descriptor(WireModel):
    name: Text
    symbol: HttpUrl
    short_desc: Text
    long_desc: Text
    images: list[HttpUrl] = Field(min_length=1)
    tags: list[TagGroup] | None = None


class GroupDescriptor(WireModel):
    name: Text


class VariantGroup(WireModel):
    id: Text
    descriptor: GroupDescriptor
    tags: list[TagGroup] = Field(min_length=1)


class EventTime(WireModel):
    label: Literal["enable", "disable"]
    timestamp: Timestamp


class Hours(WireModel):
    start: Annotated[str, StringConstraints(pattern=r"^(?:[01][0-9]|2[0-3])[0-5][0-9]$")]
    end: Annotated[str, StringConstraints(pattern=r"^(?:[01][0-9]|2[0-3])[0-5][0-9]$")]


class StoreTime(EventTime):
    # Current contract highlights legacy days/schedule as deprecated; use timing tags.
    range: Hours


class Address(WireModel):
    locality: Text
    street: Text
    city: Text
    state: Text
    area_code: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{5}$")]


class Location(WireModel):
    id: Text
    descriptor: GroupDescriptor
    gps: Annotated[str, StringConstraints(pattern=r"^-?[0-9]{1,2}\.[0-9]{4,},-?[0-9]{1,3}\.[0-9]{4,}$")]
    address: Address
    time: StoreTime

    @field_validator("gps")
    @classmethod
    def valid_coordinates(cls, value):
        latitude, longitude = map(Decimal, value.split(","))
        if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            raise ValueError("GPS coordinates outside geographic bounds")
        return value


class Contact(WireModel):
    phone: Text
    email: Annotated[str, StringConstraints(pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")]


class Fulfillment(WireModel):
    id: Text
    type: Literal["Delivery", "Self-Pickup"]
    contact: Contact


class Measure(WireModel):
    unit: Literal["unit"]
    value: Literal["1"]


class Unitized(WireModel):
    measure: Measure


class StockCount(WireModel):
    count: Annotated[str, StringConstraints(pattern=r"^(?:0|[1-9][0-9]*)$")]


class MaximumCount(WireModel):
    count: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]*$")]


class Quantity(WireModel):
    unitized: Unitized
    available: StockCount
    maximum: MaximumCount


class Price(WireModel):
    currency: Literal["INR"]
    value: Annotated[str, StringConstraints(pattern=r"^[0-9]+(?:\.[0-9]{1,2})?$")]
    maximum_value: Annotated[str, StringConstraints(pattern=r"^[0-9]+(?:\.[0-9]{1,2})?$")]

    @model_validator(mode="after")
    def within_mrp(self):
        if Decimal(self.value) > Decimal(self.maximum_value):
            raise ValueError("Selling price exceeds MRP")
        return self


class StatutoryRequirements(WireModel):
    manufacturer_or_packer_name: Text
    manufacturer_or_packer_address: Text
    common_or_generic_name_of_commodity: Text
    month_year_of_manufacture_packing_import: Annotated[str, StringConstraints(pattern=r"^(?:0[1-9]|1[0-2])/[0-9]{4}$")]


class Item(WireModel):
    id: Text
    parent_item_id: Text
    time: EventTime
    descriptor: Descriptor
    quantity: Quantity
    price: Price
    category_id: Text
    fulfillment_id: Text
    location_id: Text
    returnable: bool = Field(alias="@ondc/org/returnable")
    cancellable: bool = Field(alias="@ondc/org/cancellable")
    return_window: Duration | None = Field(default=None, alias="@ondc/org/return_window")
    seller_pickup_return: bool = Field(alias="@ondc/org/seller_pickup_return")
    time_to_ship: Duration = Field(alias="@ondc/org/time_to_ship")
    available_on_cod: bool = Field(alias="@ondc/org/available_on_cod")
    consumer_care: Text = Field(alias="@ondc/org/contact_details_consumer_care")
    statutory: StatutoryRequirements = Field(alias="@ondc/org/statutory_reqs_packaged_commodities")
    tags: list[TagGroup] = Field(min_length=1)

    @model_validator(mode="after")
    def fashion_rules(self):
        category_definition(self.category_id)
        if self.returnable and not self.return_window:
            raise ValueError("Returnable item requires return_window")
        groups = [g for g in self.tags if g.code == "attribute"]
        if len(groups) != 1:
            raise ValueError("Exactly one fashion attribute group is required")
        attributes = {tag.code: tag.value for tag in groups[0].list}
        if len(attributes) != len(groups[0].list):
            raise ValueError("Duplicate fashion attribute code")
        validate_attributes(self.category_id, attributes)
        parts = self.consumer_care.split(",")
        if len(parts) != 3 or not all(p.strip() for p in parts) or "@" not in parts[1]:
            raise ValueError("Consumer care requires name,email,phone")
        return self


class Provider(WireModel):
    id: Text
    time: EventTime
    descriptor: Descriptor
    ttl: Duration
    fulfillments: list[Fulfillment] = Field(min_length=1)
    locations: list[Location] = Field(min_length=1)
    categories: list[VariantGroup] = Field(min_length=1)
    items: list[Item] = Field(min_length=1)
    tags: list[TagGroup] = Field(min_length=1)

    @model_validator(mode="after")
    def references(self):
        for name in ["items", "locations", "categories", "fulfillments"]:
            entries = getattr(self, name)
            if len({entry.id for entry in entries}) != len(entries):
                raise ValueError(f"Duplicate {name} identifier")
        locations = {location.id for location in self.locations}
        groups = {group.id for group in self.categories}
        fulfillments = {fulfillment.id for fulfillment in self.fulfillments}
        for item in self.items:
            if item.location_id not in locations or item.parent_item_id not in groups or item.fulfillment_id not in fulfillments:
                raise ValueError("Item references missing location, variant group or fulfillment")
        return self


class Catalog(WireModel):
    descriptor: Descriptor = Field(alias="bpp/descriptor")
    providers: list[Provider] = Field(alias="bpp/providers", min_length=1)

    @model_validator(mode="after")
    def inventory_seller(self):
        if len({p.id for p in self.providers}) != len(self.providers):
            raise ValueError("Duplicate provider identifier")
        terms = [tag.value for group in (self.descriptor.tags or []) if group.code == "bpp_terms" for tag in group.list if tag.code == "np_type"]
        if terms != ["ISN"]:
            raise ValueError("Inventory seller catalog must declare np_type ISN")
        return self


class CatalogMessage(WireModel):
    catalog: Catalog


class OnSearchResponse(WireModel):
    context: Context
    message: CatalogMessage

    @model_validator(mode="after")
    def callback_context(self):
        if self.context.action != "on_search":
            raise ValueError("Catalog callback requires on_search action")
        context_time = datetime.fromisoformat(self.context.timestamp.replace("Z", "+00:00"))
        for provider in self.message.catalog.providers:
            for event in [provider.time, *(location.time for location in provider.locations), *(item.time for item in provider.items)]:
                if datetime.fromisoformat(event.timestamp.replace("Z", "+00:00")) > context_time:
                    raise ValueError("Catalog event timestamp exceeds context timestamp")
        return self
