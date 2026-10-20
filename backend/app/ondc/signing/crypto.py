
"""ONDC libsodium Ed25519 / BLAKE2b-512; sign and verify exact HTTP entity bytes."""
import base64
import hashlib
import re
import time
from dataclasses import dataclass
from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError

class SignatureError(ValueError):
    pass

def decode(value: str, length: int) -> bytes:
    try:
        result = base64.b64decode(value, validate=True)
        if len(result) != length:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise SignatureError("Invalid key or signature encoding") from None

def generate_keys() -> tuple[str, str]:
    key = SigningKey.generate()
    public = bytes(key.verify_key)
    return base64.b64encode(bytes(key) + public).decode(), base64.b64encode(public).decode()

def private_key(value: str) -> SigningKey:
    raw = decode(value, 64)
    key = SigningKey(raw[:32])
    if bytes(key.verify_key) != raw[32:]:
        raise SignatureError("Inconsistent private key")
    return key

def digest(body: bytes) -> str:
    return base64.b64encode(hashlib.blake2b(body, digest_size=64).digest()).decode()

def signing_string(body: bytes, created: int, expires: int) -> bytes:
    return f"(created): {created}\n(expires): {expires}\ndigest: BLAKE-512={digest(body)}".encode()

@dataclass(frozen=True)
class Authorization:
    subscriber_id: str
    key_id: str
    created: int
    expires: int
    signature: str

def parse(header: str | None) -> Authorization:
    if not header or len(header) > 4096 or not header.startswith("Signature "):
        raise SignatureError("Missing or malformed Authorization")
    rest = header[10:]
    fields = {}
    while rest:
        match = re.match(r'\s*([A-Za-z]+)="([^"\r\n]*)"\s*(?:,|$)', rest)
        if not match or match[1] in fields:
            raise SignatureError("Malformed Authorization")
        fields[match[1]] = match[2]
        rest = rest[match.end():]
    if set(fields) != {"keyId", "algorithm", "created", "expires", "headers", "signature"}:
        raise SignatureError("Malformed Authorization")
    parts = fields["keyId"].split("|")
    if len(parts) != 3 or not all(parts) or parts[2] != "ed25519" or fields["algorithm"] != "ed25519":
        raise SignatureError("Unsupported key identity or algorithm")
    if fields["headers"] != "(created) (expires) digest":
        raise SignatureError("Unsupported signed headers")
    if not all(re.fullmatch(r"[0-9]{1,12}", fields[k]) for k in ("created", "expires")):
        raise SignatureError("Invalid signature timestamp")
    decode(fields["signature"], 64)
    return Authorization(parts[0], parts[1], int(fields["created"]), int(fields["expires"]), fields["signature"])

def verify(body: bytes, auth: Authorization, public: str, *, now: int | None = None) -> None:
    now = int(time.time()) if now is None else now
    if not auth.created <= now < auth.expires or auth.created >= auth.expires:
        raise SignatureError("Signature outside validity window")
    try:
        VerifyKey(decode(public, 32)).verify(signing_string(body, auth.created, auth.expires), decode(auth.signature, 64))
    except BadSignatureError:
        raise SignatureError("Invalid signature") from None

def sign(body: bytes, *, subscriber_id: str, key_id: str, private: str,
         created: int | None = None, expires: int | None = None) -> str:
    if not all(re.fullmatch(r'[A-Za-z0-9._:-]+', v) for v in (subscriber_id, key_id)):
        raise SignatureError("Unsafe signing identity")
    created = int(time.time()) if created is None else created
    expires = created + 30 if expires is None else expires
    if type(created) is not int or type(expires) is not int or expires <= created:
        raise SignatureError("Invalid signature window")
    signature = base64.b64encode(private_key(private).sign(signing_string(body, created, expires)).signature).decode()
    return (f'Signature keyId="{subscriber_id}|{key_id}|ed25519",algorithm="ed25519",'
            f'created="{created}",expires="{expires}",headers="(created) (expires) digest",signature="{signature}"')
