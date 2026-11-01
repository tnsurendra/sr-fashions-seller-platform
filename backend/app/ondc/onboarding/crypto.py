"""Crypto formats used by ONDC's official subscription reference utility."""
import base64
from cryptography.hazmat.primitives import hashes, padding, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from nacl.signing import SigningKey
from app.ondc.signing.crypto import decode, private_key, SignatureError

X25519_DER_PREFIX = bytes.fromhex("302a300506032b656e032100")

def generate_encryption_keys() -> tuple[str, str]:
    key = x25519.X25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(private).decode(), base64.b64encode(public).decode()

def encryption_private(value: str) -> x25519.X25519PrivateKey:
    return x25519.X25519PrivateKey.from_private_bytes(decode(value, 32))

def encryption_public(value: str) -> x25519.X25519PublicKey:
    try:
        der = base64.b64decode(value, validate=True)
        key = serialization.load_der_public_key(der)
    except Exception as exc:
        raise SignatureError("Invalid X25519 public key encoding") from exc
    if not isinstance(key, x25519.X25519PublicKey):
        raise SignatureError("Encryption key must be X25519 SubjectPublicKeyInfo DER")
    return key

def sign_request_id(request_id: str, signing_private: str) -> str:
    if not request_id or len(request_id) > 256:
        raise SignatureError("Invalid onboarding request ID")
    return base64.b64encode(private_key(signing_private).sign(request_id.encode()).signature).decode()

def decrypt_challenge(challenge: str, own_private: str, registry_public: str) -> str:
    """X25519 shared secret + AES-256-ECB/PKCS7, matching the reference utility."""
    shared = encryption_private(own_private).exchange(encryption_public(registry_public))
    try:
        ciphertext = base64.b64decode(challenge, validate=True)
        decryptor = Cipher(algorithms.AES(shared), modes.ECB()).decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(128).unpadder()
        return (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
    except Exception as exc:
        raise SignatureError("Invalid onboarding challenge") from exc
