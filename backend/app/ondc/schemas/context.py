"""RET12 discovery context. IDs remain strings: official samples use T1/M1."""
from typing import Annotated, Literal
from urllib.parse import urlsplit
from pydantic import StringConstraints, model_validator
from app.ondc.schemas.base import Duration, HttpUrl, Text, Timestamp, WireModel
from app.ondc.utils.validation import duration_seconds


class Context(WireModel):
    domain: Literal["ONDC:RET12"]
    country: Literal["IND"]
    city: Annotated[str, StringConstraints(pattern=r"^(?:std:[0-9]+|\*)$")]
    action: Literal["search", "on_search", "select", "on_select", "init", "on_init", "confirm", "on_confirm",
                    "status", "on_status", "cancel", "on_cancel", "update", "on_update"]
    core_version: Literal["1.2.5"]
    bap_id: Text
    bap_uri: HttpUrl
    transaction_id: Text
    message_id: Text
    timestamp: Timestamp
    bpp_id: Text | None = None
    bpp_uri: HttpUrl | None = None
    key: Text | None = None  # Official context public encryption key, never a private key.
    ttl: Duration | None = None

    @model_validator(mode="after")
    def discovery_constraints(self):
        if urlsplit(self.bap_uri).hostname != self.bap_id:
            raise ValueError("bap_uri hostname must match bap_id")
        if self.bpp_uri is not None and self.bpp_id is not None and urlsplit(self.bpp_uri).hostname != self.bpp_id:
            raise ValueError("bpp_uri hostname must match bpp_id")
        if self.action in {"search", "select", "init", "confirm", "status", "cancel", "update"} and self.ttl is not None and duration_seconds(self.ttl) > 30:
            raise ValueError("request TTL must not exceed PT30S")
        if self.action.startswith("on_") and (not self.bpp_id or not self.bpp_uri):
            raise ValueError("callback context requires seller identity and URI")
        return self
