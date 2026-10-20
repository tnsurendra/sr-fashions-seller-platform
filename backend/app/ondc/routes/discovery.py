
"""Thin protocol route; seller administration remains independent."""
import json
from urllib.parse import urlsplit
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from jsonschema import ValidationError as SchemaValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.database import get_db, get_engine
from app.ondc.config import get_ondc_settings, RouteSettings
from app.ondc.registry.client import RegistryClient, RegistryError, SubscriberNotFound
from app.ondc.clients.http import SignedClient
from app.ondc.protocol.service import DiscoveryService
from app.ondc.protocol.responses import ack, nack, ProtocolError
from app.ondc.protocol.replay import ReplayConflict
from app.ondc.protocol.errors import DiscoveryError
from app.ondc.signing.crypto import SignatureError
from app.ondc.validators.discovery import validate_search, validation_nack

router = APIRouter()
# Deployment route prefix is nonsecret and must not require signing configuration at admin startup.
prefix = RouteSettings().route_prefix

def get_service(request: Request):
    service = getattr(request.app.state, "ondc_service", None)
    if service is None:
        settings = get_ondc_settings()
        if urlsplit(settings.subscriber_url).path.rstrip("/") != prefix:
            raise ValueError("ONDC route prefix must match subscriber URL path")
        service = DiscoveryService(settings, RegistryClient(settings), SignedClient(settings))
        request.app.state.ondc_service = service
    return service

async def send_callback(request, service, identity):
    # Tests can inject a session factory; never reuse a request-scoped session.
    factory = getattr(request.app.state, "ondc_session_factory", None)
    try:
        with factory() if factory else Session(get_engine()) as db:
            await service.dispatch(db, identity)
    except SQLAlchemyError:
        # Persisted pending work is recoverable; don't log SQL parameters or payloads.
        import logging
        logging.getLogger(__name__).error("ONDC callback database unavailable")

def failure(code, message, status=200, kind="DOMAIN-ERROR"):
    return JSONResponse(status_code=status, content=nack(ProtocolError(type=kind, code=code, message=message)))

def object_without_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON key")
        obj[key] = value
    return obj

@router.post(prefix + "/search", tags=["ONDC discovery"])
async def search(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > 1_000_000:
                return failure("30000", "Request entity too large")
        raw = bytes(chunks)
        if len(raw) > 1_000_000 or request.headers.get("content-encoding"):
            return failure("30000", "Unsupported request entity")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=object_without_duplicates,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        parsed = validate_search(payload)
        service = get_service(request)
        identity = await service.accept(db, parsed, raw, request.headers)
        background.add_task(send_callback, request, service, identity)
        return ack()
    except (ValidationError, SchemaValidationError) as exc:
        return JSONResponse(content=validation_nack(exc))
    except (SignatureError, SubscriberNotFound):
        return failure("30016", "Signature verification failed", 401)
    except DiscoveryError as exc:
        return failure(exc.code, exc.safe_message)
    except ReplayConflict:
        return failure("30022", "Stale or conflicting message")
    except RegistryError:
        return failure("31001", "Verification service unavailable", 503)
    except (ValueError, TypeError, UnicodeError):
        return failure("30000", "Invalid or unsupported discovery request")
    except SQLAlchemyError:
        db.rollback()
        return failure("31001", "Discovery persistence unavailable", 503)
