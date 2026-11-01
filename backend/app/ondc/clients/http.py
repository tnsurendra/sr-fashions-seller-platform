
"""Reusable signed HTTP transport. No logging of payloads or Authorization."""
import gzip
import json
import httpx
from urllib.parse import urlsplit
import ipaddress
from app.ondc.signing.crypto import sign
from app.ondc.protocol.responses import ProtocolResponse
from app.operations import increment

class CallbackError(RuntimeError):
    pass

class CallbackRejected(CallbackError):
    def __init__(self, code, message=None):
        super().__init__("Callback rejected")
        self.code = code
        self.safe_message = (message or "Callback rejected")[:500]

def serialize(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")

class SignedClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.transport = transport

    async def post(self, url: str, payload: dict, *, compress=False, acknowledge=True, extra_headers=None):
        hostname = urlsplit(url).hostname or ""
        if hostname == "prod.registry.ondc.org" or self.settings.environment == "production":
            raise CallbackError("Production communication disabled")
        if self.transport is None and not self.settings.external_network_enabled:
            try:
                local = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                local = hostname == "localhost"
            if not (self.settings.environment == "local" and local):
                raise CallbackError("External communication disabled")
        raw = serialize(payload)
        secret = self.settings.signing_private_key
        if secret is None:
            raise CallbackError("Signing key unavailable")
        headers = {"Content-Type": "application/json", "Authorization": sign(raw,
            subscriber_id=self.settings.subscriber_id, key_id=self.settings.unique_key_id,
            private=secret.get_secret_value())}
        for key, value in (extra_headers or {}).items():
            if key.lower() in {"authorization", "content-type", "content-encoding"}:
                raise CallbackError("Unsafe callback header")
            headers[key] = value
        if compress:
            headers["Content-Encoding"] = "gzip"
        try:
            async with httpx.AsyncClient(timeout=self.settings.http_timeout, transport=self.transport,
                                         follow_redirects=False, trust_env=False) as client:
                response = await client.post(url, content=gzip.compress(raw, mtime=0) if compress else raw, headers=headers)
                response.raise_for_status()
                result = response.json()
                if acknowledge:
                    parsed = ProtocolResponse.model_validate(result)
                    if parsed.message.ack.status != "ACK":
                        increment("callback_rejected_total")
                        raise CallbackRejected(parsed.error.code, parsed.error.message)
                increment("callback_delivered_total")
                return result
        except (httpx.HTTPError, ValueError):
            increment("callback_failed_total")
            raise CallbackError("HTTP callback failed") from None
