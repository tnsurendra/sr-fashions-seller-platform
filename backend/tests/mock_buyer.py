
"""Development/test buyer only. No production application imports this module."""
import gzip
import json
from fastapi import FastAPI, Request
from app.ondc.clients.http import serialize
from app.ondc.signing.crypto import sign, parse, verify
from app.ondc.validators.discovery import validate_catalog_callback
from app.ondc.protocol.responses import ack
from app.ondc.catalog.discovery import utc_now

class MockBuyer:
    def __init__(self, private, seller_public, *, subscriber_id="buyer.example.com", subscriber_url="https://buyer.example.com/ondc"):
        self.subscriber_id, self.subscriber_url = subscriber_id, subscriber_url
        self.private, self.seller_public = private, seller_public
        self.app = FastAPI(title="Local discovery test buyer")
        self.callbacks = []
        self.expected = set()

        @self.app.post("/ondc/on_search")
        async def on_search(request: Request):
            raw = await request.body()
            if request.headers.get("content-encoding") == "gzip":
                raw = gzip.decompress(raw)
            auth = parse(request.headers.get("authorization"))
            verify(raw, auth, self.seller_public)
            callback = validate_catalog_callback(json.loads(raw))
            if auth.subscriber_id != callback.context.bpp_id:
                raise ValueError("Seller signature identity mismatch")
            correlation = (callback.context.transaction_id, callback.context.message_id)
            if correlation not in self.expected:
                raise ValueError("Unexpected callback correlation")
            self.callbacks.append(callback.to_wire())
            return ack()

    def search(self, transaction="local-fashion-T1", message="local-fashion-M1"):
        payload = {"context": {"domain": "ONDC:RET12", "country": "IND", "city": "std:080",
            "action": "search", "core_version": "1.2.5", "bap_id": self.subscriber_id,
            "bap_uri": self.subscriber_url, "transaction_id": transaction,
            "message_id": message, "timestamp": utc_now(), "ttl": "PT30S"},
            "message": {"intent": {"category": {"id": "Shirts"}}}}
        self.expected.add((transaction, message))
        return payload

    def signed(self, payload):
        raw = serialize(payload)
        return raw, {"Content-Type": "application/json", "Authorization": sign(raw,
                    subscriber_id=self.subscriber_id, key_id="buyer-key", private=self.private)}

    def send(self, seller_client, payload):
        raw, headers = self.signed(payload)
        response = seller_client.post("/search", content=raw, headers=headers)
        assert response.json() == ack()
        return response
