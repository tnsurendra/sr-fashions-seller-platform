"""Small dependency-free operational controls and process-local metrics."""
import json
import logging
import time
import uuid
import secrets
from collections import Counter, defaultdict, deque
from threading import Lock
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger("sr_fashions.http")
_metrics = Counter()
_rate = defaultdict(deque)
_lock = Lock()

def increment(name: str, value: int = 1):
    with _lock:
        _metrics[name] += value

def metrics_snapshot() -> dict[str, int]:
    with _lock:
        return dict(_metrics)

class OperationalMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_request_bytes: int, requests_per_minute: int = 120,
                 enforce_admin: bool = False, admin_token: str | None = None):
        super().__init__(app)
        self.max_request_bytes = max_request_bytes
        self.requests_per_minute = requests_per_minute
        self.enforce_admin = enforce_admin
        self.admin_token = admin_token

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", "")
        try:
            uuid.UUID(request_id)
        except (ValueError, AttributeError):
            request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        if (self.enforce_admin and request.url.path.startswith("/api/") and
                request.method not in {"GET", "HEAD", "OPTIONS"}):
            supplied = request.headers.get("x-admin-token")
            if not self.admin_token or not supplied or not secrets.compare_digest(supplied, self.admin_token):
                return JSONResponse({"detail": "Administrative operator permission required", "request_id": request_id}, 401)
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > self.max_request_bytes):
            return JSONResponse({"detail": "Request body too large", "request_id": request_id}, 413)
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with _lock:
            window = _rate[client]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= self.requests_per_minute:
                _metrics["http_rate_limited_total"] += 1
                return JSONResponse({"detail": "Rate limit exceeded", "request_id": request_id}, 429)
            window.append(now)
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        increment(f"http_status_{response.status_code}_total")
        logger.info(json.dumps({"event": "http_request", "request_id": request_id,
            "method": request.method, "path": request.url.path, "status": response.status_code,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2)}))
        return response
