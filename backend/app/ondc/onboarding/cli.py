"""Read-only ONDC readiness checks. This module never calls /subscribe."""
import argparse
import json
import ssl
import urllib.request
from urllib.parse import urljoin
from app.ondc.config import get_ondc_settings
from app.ondc.onboarding.crypto import encryption_public
from app.ondc.onboarding.service import subscription_preview, verification_signature
from app.ondc.signing.crypto import decode, private_key

def report(check_public: bool = False) -> dict:
    result = {"ready": True, "checks": {}, "warnings": [], "network_requests": []}
    try:
        settings = get_ondc_settings()
        result["checks"]["configuration"] = "pass"
        decode(settings.signing_public_key or "", 32)
        encryption_public(settings.encryption_public_key or "")
        private_key(settings.signing_private_key.get_secret_value() if settings.signing_private_key else "")
        verification_signature(settings)
        result["checks"]["key_formats_and_site_signature"] = "pass"
        result["subscription_preview"] = subscription_preview(settings)
        result["checks"]["seller_role"] = "pass"
        if check_public:
            context = ssl.create_default_context()
            target = urljoin(settings.subscriber_url.rstrip("/") + "/", "ondc-site-verification.html")
            with urllib.request.urlopen(target, context=context, timeout=10) as response:
                body = response.read(65536).decode("utf-8")
            result["network_requests"].append(target)
            if "ondc-site-verification" not in body:
                raise ValueError("Public verification page is missing its meta tag")
            result["checks"]["public_https_verification"] = "pass"
        else:
            result["warnings"].append("Public HTTPS and Registry lookup not checked; use --check-public after authorization and deployment")
    except Exception as exc:
        result["ready"] = False
        result["error"] = str(exc)
    return result

def main():
    parser = argparse.ArgumentParser(description="Read-only ONDC PreProd readiness report")
    parser.add_argument("--check-public", action="store_true", help="GET the configured public verification page; never contacts /subscribe")
    args = parser.parse_args()
    value = report(args.check_public)
    print(json.dumps(value, indent=2))
    raise SystemExit(0 if value["ready"] else 1)

if __name__ == "__main__":
    main()
