"""Header authentication for internal state-changing administration only."""
import secrets
from fastapi import Header, HTTPException, Request
from app.config import get_settings

def require_admin(request: Request, x_admin_token: str | None = Header(default=None)):
    configured = getattr(request.app.state, "admin_api_token", None)
    if configured is None:
        secret = get_settings().admin_api_token
        configured = secret.get_secret_value() if secret else None
    if not configured:
        raise HTTPException(503, "Administrative authentication is not configured")
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, configured):
        raise HTTPException(401, "Administrative authentication required")
    return True
