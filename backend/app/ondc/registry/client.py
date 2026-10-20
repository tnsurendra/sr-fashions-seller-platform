
"""Signed v2.0 lookup, bounded positive caching, exact record/key binding."""
import time
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, Field
from app.ondc.schemas.base import HttpUrl, Timestamp, Text
from app.ondc.signing.crypto import decode
from app.ondc.clients.http import SignedClient, CallbackError

class RegistryError(RuntimeError):
    pass

class SubscriberNotFound(RegistryError):
    pass

class Subscriber(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)
    subscriber_id: Text
    ukId: Text
    subscriber_url: HttpUrl
    country: Text
    domain: Text
    type: Text
    status: Text
    signing_public_key: Text
    valid_from: Timestamp
    valid_until: Timestamp
    city: Text

class RegistryClient:
    def __init__(self, settings, transport=None):
        self.settings = settings
        self.http = SignedClient(settings, transport)
        self.cache = {}

    async def lookup(self, subscriber_id: str, key_id: str, *, kind="BAP", city=None) -> Subscriber:
        city = self.settings.city if city in (None, "*") else city
        key = (subscriber_id, key_id, kind, city)
        now = time.time()
        cached = self.cache.get(key)
        if cached and cached[0] > now:
            return cached[1]
        if not self.settings.registry_url:
            raise RegistryError("Registry URL not configured")
        try:
            result = await self.http.post(self.settings.registry_url, {
                "subscriber_id": subscriber_id, "ukId": key_id, "country": self.settings.country,
                "domain": self.settings.domain, "city": city, "type": kind}, acknowledge=False)
            if not isinstance(result, list):
                raise ValueError()
            matches = []
            for data in result:
                record = Subscriber.model_validate(data)
                start = datetime.fromisoformat(record.valid_from.replace("Z", "+00:00")).timestamp()
                end = datetime.fromisoformat(record.valid_until.replace("Z", "+00:00")).timestamp()
                decode(record.signing_public_key, 32)
                if (record.subscriber_id == subscriber_id and record.ukId == key_id and
                    record.country == self.settings.country and record.domain == self.settings.domain and
                    record.type == kind and record.city in (city, "*") and record.status == "SUBSCRIBED" and
                    start <= now < end):
                    matches.append((record, end))
            if not matches:
                raise SubscriberNotFound("Subscriber not found")
            if len(matches) != 1:
                raise ValueError()
            record, end = matches[0]
            if len(self.cache) >= 512:
                self.cache.clear()
            self.cache[key] = (min(now + self.settings.registry_cache_seconds, end), record)
            return record
        except SubscriberNotFound:
            raise
        except (CallbackError, ValueError, TypeError):
            raise RegistryError("Registry lookup failed") from None
