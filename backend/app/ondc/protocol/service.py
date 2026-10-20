
"""Separated discovery acceptance and leased durable callback dispatch."""
import logging
import time
from sqlalchemy import update, select
from app.ondc.models import DiscoveryMessage
from app.ondc.catalog.discovery import build_callback
from app.ondc.protocol.replay import existing, accept
from app.ondc.signing.security import authenticate, check_destination
from app.ondc.validators.discovery import require_fresh_context
from app.ondc.clients.http import CallbackError
from app.ondc.signing.crypto import SignatureError, private_key
from app.ondc.protocol.errors import DiscoveryError
from app.ondc.schemas.context import Context
from app.ondc.validators.discovery import validate_catalog_callback

logger = logging.getLogger(__name__)

class DiscoveryService:
    def __init__(self, settings, registry, client):
        self.settings, self.registry, self.client = settings, registry, client

    async def accept(self, db, search, raw, headers):
        if search.context.city not in ("*", self.settings.city):
            raise ValueError("City not supported")
        if search.context.bpp_id and search.context.bpp_id != self.settings.subscriber_id:
            raise ValueError("Seller identity mismatch")
        try:
            require_fresh_context(search.context)
        except ValueError:
            raise DiscoveryError("30022", "Stale or invalid message timestamp") from None
        await authenticate(raw, search, headers, self.settings, self.registry)
        if self.settings.signing_private_key is None:
            raise ValueError("Signing configuration unavailable")
        private_key(self.settings.signing_private_key.get_secret_value())
        if db.get_bind().dialect.name == "postgresql" and not db.in_transaction():
            db.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        row = existing(db, search.context, raw)
        if row:
            return row.id
        with db.no_autoflush:
            callback = build_callback(db, search, self.settings)
        try:
            require_fresh_context(search.context)
        except ValueError:
            raise DiscoveryError("30022", "Request expired during processing") from None
        row = accept(db, search, raw, callback, self.settings)
        return row.id

    async def dispatch(self, db, identity):
        now = time.time()
        token = now + self.settings.http_timeout + 60
        claimed = db.execute(update(DiscoveryMessage).where(
            DiscoveryMessage.id == identity, DiscoveryMessage.status.in_(["pending", "failed", "sending"]),
            DiscoveryMessage.lease_until < now).values(
                status="sending", lease_until=token, attempts=DiscoveryMessage.attempts + 1))
        db.commit()
        if not claimed.rowcount:
            return
        row = db.get(DiscoveryMessage, identity)
        status, failure = "delivered", None
        try:
            validate_catalog_callback(row.callback)
            try:
                require_fresh_context(Context.model_validate(row.callback["context"]))
            except ValueError:
                raise DiscoveryError("30022", "Callback expired") from None
            await check_destination(row.destination, self.settings)
            await self.client.post(row.destination, row.callback, compress=True)
        except DiscoveryError:
            status, failure = "expired", "callback_expired"
        except (CallbackError, SignatureError, ValueError):
            status, failure = "failed", "callback_failed"
            logger.warning("ONDC callback failed; discovery_record=%s", identity)
        db.execute(update(DiscoveryMessage).where(DiscoveryMessage.id == identity,
                   DiscoveryMessage.lease_until == token).values(status=status, error=failure, lease_until=0))
        db.commit()

    async def resume(self, db, limit=100):
        ids = db.scalars(select(DiscoveryMessage.id).where(
            DiscoveryMessage.status != "delivered", DiscoveryMessage.lease_until < time.time()).limit(limit)).all()
        for identity in ids:
            await self.dispatch(db, identity)
