"""Offline official reference validation.

The Google API contract takes precedence over stale generated OpenAPI fields.
Each reconciliation below is documented in docs/ONDC_SPECIFICATION.md.
"""
import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft7Validator, FormatChecker

SPEC = Path(__file__).resolve().parent / "spec"
FORMATS = FormatChecker()


@FORMATS.checks("date-time", raises=(ValueError, TypeError))
def rfc3339_format(value):
    from app.ondc.utils.validation import timestamp
    return isinstance(value, str) and bool(timestamp(value))


@FORMATS.checks("uri", raises=(ValueError, TypeError))
def absolute_uri(value):
    from urllib.parse import urlsplit
    return isinstance(value, str) and bool(urlsplit(value).scheme)


@lru_cache
def official_contract() -> dict:
    return json.loads((SPEC / "discovery-contract.json").read_text(encoding="utf-8"))


@lru_cache
def seller_error_codes() -> frozenset[str]:
    return frozenset(json.loads((SPEC / "seller-error-codes.json").read_text(encoding="utf-8")))


def reconciled_contract() -> dict:
    contract = deepcopy(official_contract())
    schemas = contract["components"]["schemas"]
    array_tags = {"type": "array", "items": {"$ref": "#/components/schemas/TagGroup"}}
    for name in ["Provider", "Category", "Item"]:
        schemas[name]["properties"]["tags"] = deepcopy(array_tags)
    schemas["Descriptor"]["properties"]["tags"] = deepcopy(array_tags)
    schemas["Intent"]["properties"]["tags"] = deepcopy(array_tags)
    schemas["IntentPayment"]["properties"]["@ondc/org/buyer_app_finder_fee_type"]["enum"] = ["amount", "percent"]
    for name in ["IntentFulfillment", "Fulfillment"]:
        schemas[name]["properties"]["type"]["enum"] = ["Delivery", "Self-Pickup", "Delivery and Self-Pickup"]
    for field, pattern in [("available", r"^(?:0|[1-9][0-9]*)$"), ("maximum", r"^[1-9][0-9]*$")]:
        schemas["ItemQuantity"]["properties"][field]["properties"]["count"] = {"type": "string", "pattern": pattern}
    schemas["Rating"]["properties"]["value"] = {"type": "string", "pattern": r"^(?:[1-4](?:\.[0-9])?|5(?:\.0)?)$"}
    schemas["Schedule"]["properties"]["holidays"]["items"] = {"type": "string", "format": "date"}
    schemas["Schedule"]["properties"]["times"]["items"] = {"type": "string", "pattern": r"^(?:[01][0-9]|2[0-3])[0-5][0-9]$"}
    for field in ["start", "end"]:
        schemas["Time"]["properties"]["range"]["properties"][field] = {"anyOf": [
            {"type": "string", "format": "date-time"},
            {"type": "string", "pattern": r"^(?:[01][0-9]|2[0-3])[0-5][0-9]$"},
        ]}
    return contract


def validate_official(payload: dict, section: str, *, reconcile: bool = True) -> None:
    document = reconciled_contract() if reconcile else deepcopy(official_contract())
    root = deepcopy(document["discovery"][section])
    root["components"] = document["components"]
    Draft7Validator(root, format_checker=FORMATS).validate(payload)
