from datetime import datetime, timezone
from urllib.parse import urlsplit
from app.ondc.config import ONDCSettings
from app.ondc.onboarding.crypto import encryption_public, sign_request_id
from app.ondc.signing.crypto import decode, private_key

def verification_signature(settings: ONDCSettings) -> str:
    if not settings.onboarding_request_id or not settings.signing_private_key:
        raise ValueError("Onboarding verification is not configured")
    return sign_request_id(settings.onboarding_request_id, settings.signing_private_key.get_secret_value())

def subscription_preview(settings: ONDCSettings) -> dict:
    if not all((settings.signing_public_key, settings.encryption_public_key, settings.onboarding_request_id)):
        raise ValueError("Public onboarding configuration is incomplete")
    decode(settings.signing_public_key, 32)
    encryption_public(settings.encryption_public_key)
    callback_path = urlsplit(settings.callback_url).path.rstrip("/") or "/"
    subscriber_path = urlsplit(settings.subscriber_url).path.rstrip("/") or "/"
    now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    return {
        "context": {"operation": {"ops_no": 2}},
        "message": {
            "request_id": settings.onboarding_request_id,
            "timestamp": now,
            "entity": {
                "country": settings.country,
                "subscriber_id": settings.subscriber_id,
                "unique_key_id": settings.unique_key_id,
                "callback_url": callback_path,
                "key_pair": {
                    "signing_public_key": settings.signing_public_key,
                    "encryption_public_key": settings.encryption_public_key,
                },
            },
            "network_participant": [{
                "subscriber_url": subscriber_path,
                "domain": settings.domain,
                "type": "sellerApp",
                "msn": False,
                "city_code": settings.supported_cities,
            }],
        },
        "redacted": True,
        "incomplete_organization_fields": True,
    }
