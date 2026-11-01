"""Thin status, cancel and supported update protocol endpoints."""
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
from app.ondc.protocol.post_order import PostOrderService
from app.ondc.protocol.responses import ack, nack, ProtocolError
from app.ondc.protocol.replay import ReplayConflict
from app.ondc.protocol.errors import DiscoveryError
from app.ondc.signing.crypto import SignatureError
from app.ondc.schemas.post_order import StatusRequest, CancelRequest, UpdateRequest
from app.ondc.routes.discovery import object_without_duplicates, send_callback

router = APIRouter()
prefix = RouteSettings().route_prefix
models = {"status": StatusRequest, "cancel": CancelRequest, "update": UpdateRequest}

def service(request):
    current = getattr(request.app.state, "ondc_post_order_service", None)
    if current is None:
        settings = get_ondc_settings()
        current = PostOrderService(settings, RegistryClient(settings), SignedClient(settings))
        request.app.state.ondc_post_order_service = current
    return current

def failure(code, message, status=200):
    return JSONResponse(status_code=status, content=nack(ProtocolError(type="DOMAIN-ERROR", code=code, message=message)))

async def handle(action, request, background, db):
    try:
        raw = await request.body()
        if len(raw) > 1_000_000 or request.headers.get("content-encoding"):
            return failure("30000", "Unsupported request entity")
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=object_without_duplicates,
                             parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        parsed = models[action].model_validate(payload)
        current = service(request)
        identity = await current.accept(db, parsed, raw, request.headers)
        background.add_task(send_callback, request, current, identity)
        return ack()
    except ValidationError: return failure("30000", "Invalid request")
    except (SignatureError, SubscriberNotFound): return failure("30016", "Signature verification failed", 401)
    except DiscoveryError as exc: return failure(exc.code, exc.safe_message)
    except ReplayConflict: return failure("30022", "Stale or conflicting message")
    except RegistryError: return failure("31001", "Verification service unavailable", 503)
    except (ValueError, TypeError, UnicodeError): return failure("30000", "Invalid or unsupported request")
    except SQLAlchemyError:
        db.rollback(); return failure("31001", "Order persistence unavailable", 503)

@router.post(prefix + "/status", tags=["ONDC post-order"])
async def status(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    return await handle("status", request, background, db)
@router.post(prefix + "/cancel", tags=["ONDC post-order"])
async def cancel(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    return await handle("cancel", request, background, db)
@router.post(prefix + "/update", tags=["ONDC post-order"])
async def update(request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    return await handle("update", request, background, db)
