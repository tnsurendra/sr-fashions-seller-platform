
"""Inbound identity verification and outbound destination checks."""
import ipaddress
import socket
import asyncio
from urllib.parse import urlsplit
from app.ondc.signing.crypto import parse, verify, SignatureError

async def check_destination(url, settings):
    parsed = urlsplit(url)
    if parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise SignatureError("Unsafe callback destination")
    if settings.environment == "local" and settings.allow_local_callbacks:
        return
    if parsed.scheme != "https":
        raise SignatureError("Callback requires HTTPS")
    try:
        addresses = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, parsed.port or 443)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
            raise SignatureError("Callback destination is not public")
    except OSError:
        raise SignatureError("Callback destination cannot be resolved") from None

async def authenticate(raw, request, headers, settings, registry):
    auth = parse(headers.get("authorization"))
    if auth.subscriber_id != request.context.bap_id:
        raise SignatureError("Buyer identity mismatch")
    buyer = await registry.lookup(auth.subscriber_id, auth.key_id, kind="BAP", city=request.context.city)
    verify(raw, auth, buyer.signing_public_key)
    if buyer.subscriber_url.rstrip("/") != request.context.bap_uri.rstrip("/"):
        raise SignatureError("Callback URI differs from registered buyer URI")
    gateway = headers.get("x-gateway-authorization")
    if gateway:
        gateway_auth = parse(gateway)
        record = await registry.lookup(gateway_auth.subscriber_id, gateway_auth.key_id, kind="BG", city=request.context.city)
        verify(raw, gateway_auth, record.signing_public_key)
    elif not (settings.environment == "local" and settings.allow_local_peer_search):
        raise SignatureError("Gateway Authorization required")
    await check_destination(request.context.bap_uri, settings)
