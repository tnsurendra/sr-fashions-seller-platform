from html import escape
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, StringConstraints
from typing import Annotated
from app.ondc.config import get_ondc_settings, RouteSettings
from app.ondc.onboarding.crypto import decrypt_challenge, SignatureError
from app.ondc.onboarding.service import verification_signature

router = APIRouter(include_in_schema=False)
prefix = RouteSettings().route_prefix
SafeText = Annotated[str, StringConstraints(min_length=1, max_length=4096)]

class Challenge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subscriber_id: SafeText
    challenge: SafeText

@router.get("/ondc-site-verification.html", response_class=HTMLResponse)
def site_verification():
    try:
        signature = verification_signature(get_ondc_settings())
    except (ValueError, SignatureError):
        raise HTTPException(503, "ONDC onboarding verification is not configured") from None
    return HTMLResponse(f"<!doctype html><html><head><meta name='ondc-site-verification' content='{escape(signature)}'></head><body>ONDC Site Verification Page</body></html>")

@router.post(f"{prefix}/on_subscribe")
def on_subscribe(payload: Challenge):
    settings = get_ondc_settings()
    if payload.subscriber_id != settings.subscriber_id:
        raise HTTPException(400, "Subscriber identity mismatch")
    if not settings.encryption_private_key or not settings.registry_public_key:
        raise HTTPException(503, "ONDC onboarding challenge handling is not configured")
    try:
        answer = decrypt_challenge(payload.challenge, settings.encryption_private_key.get_secret_value(), settings.registry_public_key)
    except SignatureError:
        raise HTTPException(400, "Invalid onboarding challenge") from None
    return {"answer": answer}
