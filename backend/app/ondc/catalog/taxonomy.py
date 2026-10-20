"""Official sheet snapshot. Internal retailer category names are never taxonomy codes."""
import json
import re
from functools import lru_cache
from pathlib import Path
from app.ondc.utils.validation import http_url


@lru_cache
def taxonomy() -> dict:
    return json.loads((Path(__file__).resolve().parents[1] / "protocol/spec/ret12-taxonomy.json").read_text(encoding="utf-8"))["categories"]


def category_definition(category: str) -> dict:
    if category not in taxonomy():
        raise ValueError(f"Unknown official RET12 category: {category}")
    return taxonomy()[category]


def attribute_code(label: str) -> str:
    # API contract note 384: e.g. Size Chart => size_chart.
    return label.lower().replace(" ", "_")


def validate_attributes(category: str, attributes: dict[str, str]) -> None:
    definition = category_definition(category)
    allowed = {attribute_code(label) for label in definition["mandatory"] + definition["optional"]}
    allowed.add("colour_name")
    unknown = set(attributes) - allowed
    if unknown:
        raise ValueError(f"Attributes outside category taxonomy: {sorted(unknown)}")
    required = {attribute_code(label) for label in definition["mandatory"]} - {"colour"}
    missing = {key for key in required if not attributes.get(key)}
    if missing:
        raise ValueError(f"Missing mandatory fashion attributes: {sorted(missing)}")
    colour = attributes.get("colour")
    if colour:
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", colour):
            raise ValueError("colour must be a six-digit hex code")
        if not attributes.get("colour_name"):
            raise ValueError("colour_name is required with colour hex")
    elif not attributes.get("colour_name"):
        raise ValueError("A colour name is required when a hex code is unavailable")
    if attributes.get("size_chart"):
        http_url(attributes["size_chart"])
    # Attribute enums are suggestive (API contract note 384), not exhaustive.
