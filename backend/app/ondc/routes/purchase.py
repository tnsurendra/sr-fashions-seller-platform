"""Thin authenticated endpoints for select, init and confirm."""
import json
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.database import get_db
from app.ondc.config import get_ondc_settings, RouteSettings
from app.ondc.registry.client import RegistryClient, RegistryError, SubscriberNotFound
from app.ondc.clients.http import SignedClient
from app.ondc.protocol.purchase import PurchaseService
from app.ondc.protocol.responses import ack, nack, ProtocolError
from app.ondc.protocol.replay import ReplayConflict
from app.ondc.protocol.errors import DiscoveryError
from app.ondc.signing.crypto import SignatureError
from app.ondc.schemas.orders import SelectRequest, InitRequest, ConfirmRequest
from app.ondc.routes.discovery import object_without_duplicates, send_callback

router = APIRouter()
prefix = RouteSettings().route_prefix
models = {"select": SelectRequest, "init": InitRequest, "confirm": ConfirmRequest}

def service(request):
    current = getattr(request.app.state, "ondc_purchase_service", None)
    if current is None:
        settings = get_ondc_settings()
        current = PurchaseService(settings, RegistryClient(settings), SignedClient(settings))
        request.app.state.ondc_purchase_service = current
    return current

def failure(code, message, status=200, kind="DOMAIN-ERROR"):
    return JSONResponse(status_code=status, content=nack(ProtocolError(type=kind, code=code, message=message)))

async def handle(action, request, background, db):
    try:
        chunks = bytearray()
        async for chunk in request.stream():
            chunks.extend(chunk)
            if len(chunks) > 1_000_000:
                return failure("30000", "Request entity too large")
        raw = bytes(chunks)
        if request.headers.get("content-encoding"):
            return failure("30000", "Unsupported request entity")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=object_without_duplicates,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        parsed = models[action].model_validate(payload)
        current = service(request)
        identity = await current.accept(db, parsed, raw, request.headers)
        background.add_task(send_callback, request, current, identity)
        return ack()
    except ValidationError:
        return failure("30000", "Invalid request")
    except (SignatureError, SubscriberNotFound):
        return failure("30016", "Signature verification failed", 401)
    except DiscoveryError as exc:
        return failure(exc.code, exc.safe_message)
    except ReplayConflict:
        return failure("30022", "Stale or conflicting message")
    except RegistryError:
        return failure("31001", "Verification service unavailable", 503)
    except (ValueError, TypeError, UnicodeError):
        return failure("30000", "Invalid or unsupported request")
    except SQLAlchemyError:
        db.rollback()
        return failure("31001", "Order persistence unavailable", 503)

@router.post(prefix + "/select", tags=["ONDC purchase"])
async def select_route(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    return await handle("select", request, background, db)

@router.post(prefix + "/init", tags=["ONDC purchase"])
async def init_route(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    return await handle("init", request, background, db)

@router.post(prefix + "/confirm", tags=["ONDC purchase"])
async def confirm_route(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    return await handle("confirm", request, background, db)
