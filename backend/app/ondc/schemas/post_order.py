"""Strict official Retail B2C 1.2.5 post-order request subset."""
from typing import Literal, List
from pydantic import Field, model_validator
from app.ondc.schemas.base import Text, WireModel
from app.ondc.schemas.context import Context

class StatusMessage(WireModel):
    order_id: Text

class StatusRequest(WireModel):
    context: Context
    message: StatusMessage
    @model_validator(mode="after")
    def action(self):
        if self.context.action != "status": raise ValueError("Expected status action")
        return self

class CancelDescriptor(WireModel):
    name: Literal["fulfillment"]
    short_desc: Text
    tags: list[dict] | None = None

class CancelMessage(WireModel):
    order_id: Text
    cancellation_reason_id: Literal["006"]
    descriptor: CancelDescriptor

class CancelRequest(WireModel):
    context: Context
    message: CancelMessage
    @model_validator(mode="after")
    def action(self):
        if self.context.action != "cancel": raise ValueError("Expected cancel action")
        return self

class ReturnTag(WireModel):
    code: Literal["return_request"]
    list: List[dict] = Field(min_length=1)

class ReturnFulfillment(WireModel):
    type: Literal["Return"]
    tags: list[ReturnTag] = Field(min_length=1, max_length=1)

class UpdateOrder(WireModel):
    id: Text
    fulfillments: list[ReturnFulfillment] = Field(min_length=1, max_length=1)

class UpdateMessage(WireModel):
    update_target: Literal["item"]
    order: UpdateOrder

class UpdateRequest(WireModel):
    context: Context
    message: UpdateMessage
    @model_validator(mode="after")
    def action(self):
        if self.context.action != "update": raise ValueError("Expected update action")
        return self

def return_values(request: UpdateRequest):
    values = {entry.get("code"): entry.get("value") for entry in request.message.order.fulfillments[0].tags[0].list}
    required = {"id", "item_id", "item_quantity", "reason_id"}
    if not required <= values.keys() or values["reason_id"] != "003":
        raise ValueError("Unsupported or invalid return request")
    if set(values) - {"id", "item_id", "parent_item_id", "item_quantity", "reason_id", "reason_desc", "images", "ttl_approval", "ttl_reverseqc"}:
        raise ValueError("Unsupported return request field")
    try: quantity = int(values["item_quantity"])
    except (TypeError, ValueError): raise ValueError("Invalid return quantity") from None
    if quantity < 1: raise ValueError("Invalid return quantity")
    return values, quantity
