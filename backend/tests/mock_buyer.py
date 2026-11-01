
"""Development/test buyer only. No production application imports this module."""
import gzip
import json
from fastapi import FastAPI, Request
from app.ondc.clients.http import serialize
from app.ondc.signing.crypto import sign, parse, verify
from app.ondc.validators.discovery import validate_catalog_callback
from app.ondc.protocol.responses import ack
from app.ondc.catalog.discovery import utc_now
from app.ondc.protocol.purchase import validate_purchase_callback
from app.ondc.protocol.post_order import validate_post_order_callback

class MockBuyer:
    def __init__(self, private, seller_public, *, subscriber_id="buyer.example.com", subscriber_url="https://buyer.example.com/ondc"):
        self.subscriber_id, self.subscriber_url = subscriber_id, subscriber_url
        self.private, self.seller_public = private, seller_public
        self.app = FastAPI(title="Local discovery test buyer")
        self.callbacks = []
        self.callback_headers = []
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
            self.callback_headers.append(dict(request.headers))
            return ack()

        async def purchase_callback(request: Request):
            raw = await request.body()
            if request.headers.get("content-encoding") == "gzip":
                raw = gzip.decompress(raw)
            auth = parse(request.headers.get("authorization"))
            verify(raw, auth, self.seller_public)
            decoded = json.loads(raw)
            callback = (validate_post_order_callback(decoded) if decoded.get("context", {}).get("action") in
                        {"on_status", "on_cancel", "on_update"} else validate_purchase_callback(decoded))
            if auth.subscriber_id != callback["context"]["bpp_id"]:
                raise ValueError("Seller signature identity mismatch")
            correlation = (callback["context"]["transaction_id"], callback["context"]["message_id"])
            if correlation not in self.expected:
                raise ValueError("Unexpected callback correlation")
            self.callbacks.append(callback)
            self.callback_headers.append(dict(request.headers))
            return ack()

        self.app.add_api_route("/ondc/on_select", purchase_callback, methods=["POST"])
        self.app.add_api_route("/ondc/on_init", purchase_callback, methods=["POST"])
        self.app.add_api_route("/ondc/on_confirm", purchase_callback, methods=["POST"])
        self.app.add_api_route("/ondc/on_status", purchase_callback, methods=["POST"])
        self.app.add_api_route("/ondc/on_cancel", purchase_callback, methods=["POST"])
        self.app.add_api_route("/ondc/on_update", purchase_callback, methods=["POST"])

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

    def context(self, action, transaction, message):
        self.expected.add((transaction, message))
        return {"domain": "ONDC:RET12", "country": "IND", "city": "std:080", "action": action,
            "core_version": "1.2.5", "bap_id": self.subscriber_id, "bap_uri": self.subscriber_url,
            "bpp_id": "seller.example.com", "bpp_uri": "https://seller.example.com",
            "transaction_id": transaction, "message_id": message, "timestamp": utc_now(), "ttl": "PT30S"}

    def send_action(self, seller_client, action, payload):
        raw, headers = self.signed(payload)
        return seller_client.post("/" + action, content=raw, headers=headers)

    def send(self, seller_client, payload):
        raw, headers = self.signed(payload)
        response = seller_client.post("/search", content=raw, headers=headers)
        assert response.json() == ack()
        return response
