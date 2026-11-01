import logging
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from app.api.routes import router
from app.config import get_settings
from app.database import get_db
from app.operations import OperationalMiddleware, metrics_snapshot
from app.ondc.admin_security import require_admin

logger = logging.getLogger(__name__)
settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(OperationalMiddleware, max_request_bytes=settings.max_request_bytes,
    requests_per_minute=120 if settings.deployment_environment in {"preprod", "production"} else 100_000,
    enforce_admin=settings.deployment_environment in {"preprod", "production"},
    admin_token=settings.admin_api_token.get_secret_value() if settings.admin_api_token else None)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
    allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization", "X-Admin-Token", "X-Request-ID"])
app.include_router(router)
from app.ondc import models as ondc_models  # isolated extensions registered for migrations
from app.ondc.catalog.administration import router as publication_router
from app.ondc.catalog.lifecycle import router as lifecycle_router
from app.ondc.routes.discovery import router as discovery_router
from app.ondc.routes.purchase import router as purchase_router
from app.ondc.routes.post_order import router as post_order_router
from app.ondc.routes.onboarding import router as onboarding_router
app.include_router(publication_router)
app.include_router(lifecycle_router)
app.include_router(discovery_router)
app.include_router(purchase_router)
app.include_router(post_order_router)
app.include_router(onboarding_router)


@app.exception_handler(IntegrityError)
def integrity_error(request, exc):
    return JSONResponse(status_code=409, content={"detail": "Conflicting data or dependent records; check unique fields and references"})


@app.exception_handler(SQLAlchemyError)
def database_error(request, exc):
    logger.error("Database request failed (%s)", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.get("/")
def root():
    return {"name": settings.app_name, "version": "0.1.0", "docs": "/docs"}


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}

@app.get("/livez", include_in_schema=False)
def livez():
    return {"status": "alive"}

@app.get("/readyz", include_in_schema=False)
def readyz(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}

@app.get("/internal/metrics", include_in_schema=False, dependencies=[Depends(require_admin)])
def operational_metrics(db: Session = Depends(get_db)):
    from app.ondc.models import CatalogPublicationJob, DiscoveryMessage
    from sqlalchemy import func, select
    values = metrics_snapshot()
    values["callback_pending"] = db.scalar(select(func.count()).select_from(DiscoveryMessage).where(DiscoveryMessage.status.in_(["pending", "failed", "sending"]))) or 0
    values["catalog_jobs_pending"] = db.scalar(select(func.count()).select_from(CatalogPublicationJob).where(CatalogPublicationJob.status.in_(["pending", "failed", "sending"]))) or 0
    return values
