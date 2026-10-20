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

logger = logging.getLogger(__name__)
settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
    allow_credentials=False, allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"])
app.include_router(router)
from app.ondc import models as ondc_models  # isolated extensions registered for migrations
from app.ondc.catalog.administration import router as publication_router
from app.ondc.routes.discovery import router as discovery_router
app.include_router(publication_router)
app.include_router(discovery_router)


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
