"""First full-discovery flow only; no HTTP routes are registered."""
from typing import Literal
from pydantic import Field, field_validator, model_validator
from app.ondc.schemas.base import Text, WireModel
from app.ondc.schemas.context import Context
from app.ondc.schemas.tags import TagGroup


class SearchCategory(WireModel):
    id: Text | None = None

    @field_validator("id")
    @classmethod
    def fashion_category(cls, value):
        if value is not None:
            from app.ondc.catalog.taxonomy import category_definition
            category_definition(value)
        return value



class SearchDescriptor(WireModel):
    name: Text | None = None


class SearchItem(WireModel):
    descriptor: SearchDescriptor | None = None


class SearchLocation(WireModel):
    area_code: Text | None = None


class SearchEnd(WireModel):
    location: SearchLocation | None = None


class SearchFulfillment(WireModel):
    type: Literal["Delivery", "Self-Pickup", "Delivery and Self-Pickup"] | None = None
    end: SearchEnd | None = None


class SearchPayment(WireModel):
    finder_fee_type: Literal["amount", "percent"] | None = Field(default=None, alias="@ondc/org/buyer_app_finder_fee_type")
    finder_fee_amount: Text | None = Field(default=None, alias="@ondc/org/buyer_app_finder_fee_amount", pattern=r"^(?:[0-9]+)(?:\.[0-9]+)?$")


class Intent(WireModel):
    tags: list[TagGroup] | None = None
    fulfillment: SearchFulfillment | None = None
    payment: SearchPayment | None = None
    category: SearchCategory | None = None
    item: SearchItem | None = None


class SearchMessage(WireModel):
    intent: Intent


class SearchRequest(WireModel):
    context: Context
    message: SearchMessage

    @model_validator(mode="after")
    def search_action(self):
        if self.context.action != "search":
            raise ValueError("Search request requires action search")
        return self
