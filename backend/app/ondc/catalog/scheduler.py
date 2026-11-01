"""Durable, lease-based continuous incremental catalog scheduler."""
import time
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from app.ondc.models import CatalogSubscription, CatalogPublicationJob
from app.ondc.catalog.discovery import build_callback
from app.ondc.validators.discovery import validate_search
from app.ondc.clients.http import CallbackError

def iso(value):
    # Preserve the persisted window boundary. Millisecond truncation could exclude a
    # catalog mutation occurring later in the same millisecond and mark the job empty.
    return datetime.fromtimestamp(value, timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

def schedule_due(db, now=None):
    now = now or time.time()
    rows = db.scalars(select(CatalogSubscription).where(
        CatalogSubscription.status == "active", CatalogSubscription.next_run_at <= now).with_for_update(skip_locked=True)).all()
    created = 0
    for sub in rows:
        end = now
        job = CatalogPublicationJob(subscription_id=sub.id, window_start=sub.cursor_at, window_end=end,
            status="pending", next_attempt_at=now, created_at=now)
        db.add(job)
        try:
            db.flush(); created += 1
        except IntegrityError:
            db.rollback(); continue
        sub.cursor_at, sub.next_run_at, sub.updated_at = end, now + sub.interval_seconds, now
    db.commit()
    return created

async def dispatch_due(db, settings, client, limit=100, now=None):
    now = now or time.time()
    ids = db.scalars(select(CatalogPublicationJob.id).where(
        CatalogPublicationJob.status.in_(["pending", "failed"]),
        CatalogPublicationJob.next_attempt_at <= now,
        CatalogPublicationJob.lease_until < now).limit(limit)).all()
    delivered = 0
    for identity in ids:
        lease = now + settings.http_timeout + 60
        claimed = db.execute(update(CatalogPublicationJob).where(CatalogPublicationJob.id == identity,
            CatalogPublicationJob.lease_until < now,
            CatalogPublicationJob.status.in_(["pending", "failed"])).values(
                status="sending", lease_until=lease, attempts=CatalogPublicationJob.attempts + 1))
        db.commit()
        if not claimed.rowcount: continue
        job = db.get(CatalogPublicationJob, identity)
        sub = db.get(CatalogSubscription, job.subscription_id)
        payload = {"context": {"domain": settings.domain, "country": settings.country, "city": settings.city,
            "action": "search", "core_version": settings.protocol_version, "bap_id": sub.bap_id,
            "bap_uri": sub.bap_uri, "transaction_id": sub.transaction_id,
            "message_id": f"catalog-job-{job.id}", "timestamp": iso(now), "ttl": "PT30S"},
            "message": {"intent": {"tags": [{"code": "catalog_inc", "list": [
                {"code": "start_time", "value": iso(job.window_start)},
                {"code": "end_time", "value": iso(job.window_end)}]}]}}}
        try:
            callback, headers, no_changes = build_callback(db, validate_search(payload), settings)
            if not no_changes:
                await client.post(sub.bap_uri.rstrip("/") + "/on_search", callback, compress=True,
                                  extra_headers=headers)
            values = {"status": "delivered", "lease_until": 0, "error": None}
            delivered += 1
        except (CallbackError, ValueError):
            delay = min(3600, 30 * (2 ** min(job.attempts, 7)))
            values = {"status": "failed", "lease_until": 0,
                      "next_attempt_at": time.time() + delay, "error": "catalog_callback_failed"}
        db.execute(update(CatalogPublicationJob).where(CatalogPublicationJob.id == identity,
                                                        CatalogPublicationJob.lease_until == lease).values(**values))
        db.commit()
    return delivered
