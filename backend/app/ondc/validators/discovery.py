"""Reusable validation entry points for future routes. No routes are installed."""
from datetime import datetime, timedelta, timezone
from pydantic import ValidationError
from jsonschema import ValidationError as SchemaValidationError
from app.ondc.protocol.responses import ProtocolError, nack
from app.ondc.protocol.specification import validate_official
from app.ondc.schemas.context import Context
from app.ondc.schemas.discovery import SearchRequest
from app.ondc.schemas.catalog import OnSearchResponse
from app.ondc.utils.validation import duration_seconds


def validate_search(payload: dict) -> SearchRequest:
    request = SearchRequest.model_validate(payload)
    validate_official(request.to_wire(), "search")
    return request


def validate_catalog_callback(payload: dict) -> OnSearchResponse:
    callback = OnSearchResponse.model_validate(payload)
    validate_official(callback.to_wire(), "on_search")
    return callback


def validation_nack(error: ValidationError | SchemaValidationError) -> dict:
    # Do not serialize rejected input, raw exception messages or private configuration.
    if isinstance(error, ValidationError):
        location = error.errors(include_input=False, include_context=False)[0]["loc"]
    else:
        location = tuple(error.absolute_path)
    path = "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in location)
    kind = "CONTEXT-ERROR" if location and location[0] == "context" else "JSON-SCHEMA-ERROR"
    return nack(ProtocolError(type=kind, code="30000", path=path, message="Invalid protocol request"))


def require_fresh_context(context: Context, *, now: datetime | None = None) -> None:
    """Explicit opt-in freshness check; schema validation never depends on wall clock."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must include timezone")
    sent = datetime.fromisoformat(context.timestamp.replace("Z", "+00:00"))
    if sent > now:
        raise ValueError("Message timestamp is in the future")
    if context.ttl is None:
        raise ValueError("TTL required for freshness validation")
    if sent + timedelta(seconds=float(duration_seconds(context.ttl))) <= now:
        raise ValueError("Message TTL has expired")
