
"""Database uniqueness arbitrates workers; exact retries reuse persisted work."""
import hashlib
import time
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from app.ondc.models import DiscoveryMessage

class ReplayConflict(ValueError):
    pass

def replay_key(context):
    return {"sender": context.bap_id, "domain": context.domain, "action": context.action,
            "transaction_id": context.transaction_id, "message_id": context.message_id}

def existing(db, context, raw):
    row = db.scalar(select(DiscoveryMessage).filter_by(**replay_key(context)))
    if row and row.body_hash != hashlib.sha512(raw).hexdigest():
        raise ReplayConflict("Message identifier reused with a different body")
    return row

def accept(db, search, raw, callback, settings):
    row = DiscoveryMessage(**replay_key(search.context), body_hash=hashlib.sha512(raw).hexdigest(),
          request=search.to_wire(), callback=callback,
          destination=search.context.bap_uri.rstrip("/") + "/on_search",
          retain_until=time.time() + settings.replay_retention_seconds)
    db.add(row)
    try:
        db.commit()
        return row
    except IntegrityError:
        db.rollback()
        row = existing(db, search.context, raw)
        if row is None:
            raise
        return row

def cleanup(db):
    # Preserve pending/failed work for operator inspection; delivered tombstones expire.
    result = db.execute(delete(DiscoveryMessage).where(
        DiscoveryMessage.retain_until < time.time(), DiscoveryMessage.status == "delivered"))
    db.commit()
    return result.rowcount
