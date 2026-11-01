"""Required enrichment supplied by the caller; these are NOT ONDC wire fields.

Publication administration persists these validated inputs in ONDC side tables.
"""
import re
from pydantic import Field, model_validator, field_validator
from app.ondc.schemas.base import Duration, HttpUrl, Text, WireModel
from app.ondc.schemas.catalog import Address, Contact, Descriptor, Hours, StatutoryRequirements
from app.ondc.schemas.tags import TagGroup


class StorePublication(WireModel):
    enabled: bool = True
    gps: Text
    address: Address
    hours: Hours
    tags: list[TagGroup] = Field(min_length=1)
    # Optional order terms are internal publication inputs. They map to official
    # quote/fulfillment fields only when purchase flow is enabled for the store.
    delivery_charge: str | None = Field(default=None, pattern=r"^[0-9]+(?:\.[0-9]{1,2})?$")
    fulfillment_tat: Duration | None = None

    @field_validator("gps")
    @classmethod
    def coordinates(cls, value):
        from app.ondc.schemas.catalog import Location
        import re
        if not re.fullmatch(r"-?[0-9]{1,2}\.[0-9]{4,},-?[0-9]{1,3}\.[0-9]{4,}", value):
            raise ValueError("GPS requires decimal coordinates")
        return Location.valid_coordinates(value)

    @model_validator(mode="after")
    def publication_tags(self):
        pairs = set()
        for group in self.tags:
            values = {tag.code: tag.value for tag in group.list}
            if len(values) != len(group.list):
                raise ValueError("Duplicate store tag key")
            if group.code == "timing":
                required = {"type", "location", "day_from", "day_to", "time_from", "time_to"}
                if not required <= values.keys():
                    raise ValueError("Incomplete timing tags")
                if not re.fullmatch(r"[1-7]", values["day_from"]) or not re.fullmatch(r"[1-7]", values["day_to"]):
                    raise ValueError("Timing days must be from 1 to 7")
                if int(values["day_to"]) < int(values["day_from"]):
                    raise ValueError("Timing day_to must be >= day_from")
                Hours.model_validate({"start": values["time_from"], "end": values["time_to"]})
                if values["time_to"] < values["time_from"]:
                    raise ValueError("Timing time_to must be >= time_from")
            elif group.code == "serviceability":
                required = {"location", "category", "type", "val", "unit"}
                if not required <= values.keys() or values["type"] not in {"10", "11", "12", "13"}:
                    raise ValueError("Incomplete or invalid serviceability tags")
                from app.ondc.catalog.taxonomy import category_definition
                category_definition(values["category"])
                pair = (values["location"], values["category"])
                if pair in pairs:
                    raise ValueError("Only one serviceability level per location/category")
                pairs.add(pair)
                if values["type"] == "12" and (values["val"] != "IND" or values["unit"] != "country"):
                    raise ValueError("Pan-India serviceability requires IND/country")
            else:
                raise ValueError("Unsupported store tag group in publication profile")
        return self



class ProductPublication(WireModel):
    images: list[HttpUrl] = Field(min_length=1)
    attributes: dict[str, Text]
    colour_hex_by_name: dict[str, str | None]
    origin_country: Text = Field(pattern=r"^[A-Z]{3}$")
    statutory: StatutoryRequirements
    returnable: bool
    cancellable: bool
    return_window: Duration | None = None
    seller_pickup_return: bool
    time_to_ship: Duration
    available_on_cod: bool
    consumer_care: Text
    maximum_per_order: int = Field(ge=1)


class PublicationProfile(WireModel):
    bpp_descriptor: Descriptor
    provider_descriptor: Descriptor
    provider_ttl: Duration
    fulfillment_id: Text
    fulfillment_type: str = Field(pattern=r"^(?:Delivery|Self-Pickup)$")
    contact: Contact
    category_mapping: dict[str, Text]
    stores: dict[int, StorePublication]
    products: dict[int, ProductPublication]
