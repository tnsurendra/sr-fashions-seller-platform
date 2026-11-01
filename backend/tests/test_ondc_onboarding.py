import base64
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from app.ondc.config import ONDCSettings
from app.ondc.onboarding.crypto import (
    decrypt_challenge, encryption_private, encryption_public,
    generate_encryption_keys, sign_request_id,
)
from app.ondc.onboarding.service import subscription_preview
from app.ondc.signing.crypto import generate_keys

def configured_settings():
    sign_private, sign_public = generate_keys()
    enc_private, enc_public = generate_encryption_keys()
    registry_private, registry_public = generate_encryption_keys()
    settings = ONDCSettings(_env_file=None, subscriber_id="seller.example.com",
        subscriber_url="https://seller.example.com/ondc", callback_url="https://seller.example.com",
        unique_key_id="key-1", city="std:080", signing_private_key=sign_private,
        signing_public_key=sign_public, encryption_private_key=enc_private,
        encryption_public_key=enc_public, onboarding_request_id="stable-request-id",
        registry_public_key=registry_public)
    return settings, registry_private

def test_x25519_der_key_and_challenge_vector():
    settings, registry_private = configured_settings()
    shared = encryption_private(registry_private).exchange(encryption_public(settings.encryption_public_key))
    padder = padding.PKCS7(128).padder()
    padded = padder.update(b"mock-challenge-answer") + padder.finalize()
    encryptor = Cipher(algorithms.AES(shared), modes.ECB()).encryptor()
    challenge = base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()
    assert decrypt_challenge(challenge, settings.encryption_private_key.get_secret_value(), settings.registry_public_key) == "mock-challenge-answer"

def test_request_id_signature_and_seller_preview():
    settings, _ = configured_settings()
    signature = sign_request_id(settings.onboarding_request_id, settings.signing_private_key.get_secret_value())
    assert len(base64.b64decode(signature)) == 64
    preview = subscription_preview(settings)
    assert preview["context"]["operation"]["ops_no"] == 2
    assert preview["message"]["request_id"] == settings.onboarding_request_id
    assert preview["message"]["network_participant"][0] == {
        "subscriber_url": "/ondc", "domain": "ONDC:RET12", "type": "sellerApp",
        "msn": False, "city_code": ["std:080"],
    }
    assert "private" not in str(preview).lower()

def test_onboarding_routes(client, monkeypatch):
    settings, registry_private = configured_settings()
    import app.ondc.routes.onboarding as routes
    monkeypatch.setattr(routes, "get_ondc_settings", lambda: settings)
    page = client.get("/ondc-site-verification.html")
    assert page.status_code == 200
    assert "ondc-site-verification" in page.text

    shared = encryption_private(registry_private).exchange(encryption_public(settings.encryption_public_key))
    padder = padding.PKCS7(128).padder()
    padded = padder.update(b"answer-123") + padder.finalize()
    encryptor = Cipher(algorithms.AES(shared), modes.ECB()).encryptor()
    challenge = base64.b64encode(encryptor.update(padded) + encryptor.finalize()).decode()
    response = client.post("/on_subscribe", json={"subscriber_id": settings.subscriber_id, "challenge": challenge})
    assert response.status_code == 200
    assert response.json() == {"answer": "answer-123"}
    assert client.post("/on_subscribe", json={"subscriber_id": "wrong.example", "challenge": challenge}).status_code == 400

def test_operational_controls(client):
    too_large = client.post("/api/sellers", content=b"{}", headers={"content-length": "1048577"})
    assert too_large.status_code == 413
    live = client.get("/livez")
    assert live.status_code == 200
    assert live.headers["x-request-id"]
    assert client.get("/readyz").json()["status"] == "ready"
    assert client.get("/internal/metrics").status_code in {401, 503}
