"""Wire format checks sourced from Retail B2C 1.2.5; no network access."""
import re
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlsplit


def http_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Expected an absolute HTTP(S) URL without credentials or fragment")
    return value


def timestamp(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value):
        raise ValueError("Expected RFC3339 timestamp with timezone")
    datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value


def duration_seconds(value: str) -> Decimal:
    # Operational foundation supports fixed ISO8601 day/time durations.
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", value)
    if not match or not any(match.groups()) or value.endswith("T"):
        raise ValueError("Expected a fixed ISO8601 day/time duration")
    days, hours, minutes, seconds = [Decimal(v or "0") for v in match.groups()]
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def positive_duration(value: str) -> str:
    if duration_seconds(value) <= 0:
        raise ValueError("Duration must be positive")
    return value
