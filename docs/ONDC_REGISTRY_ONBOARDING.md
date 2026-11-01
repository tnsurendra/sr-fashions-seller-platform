# ONDC Registry onboarding

The implementation follows the official participant-onboarding guide and pinned Registry contract. The current official flow uses Ed25519 keys, X25519 encryption keys with the public key encoded as SubjectPublicKeyInfo DER then base64, a stable unique request ID, and the raw request ID signed without hashing.

`GET /ondc-site-verification.html` returns the signed request ID in the required meta element. The same `ONDC_ONBOARDING_REQUEST_ID` must appear in the reviewed subscription payload. `POST /on_subscribe` accepts only the configured subscriber identity and decrypts the base64 challenge using the official reference utility's X25519 shared-secret and AES-256-ECB/PKCS7 behavior. Invalid identity, key configuration, encoding or ciphertext fails safely.

The read-only CLI produces an `ops_no: 2`, `type: sellerApp`, `msn: false` preview. It intentionally marks organization fields incomplete: legal entity, GST/PAN, signatory, address, email, mobile, key validity and authorized city data must not be guessed. No function submits `/subscribe`.

PreProd lookup is fixed to `https://preprod.registry.ondc.org/v2.0/lookup`. The documented subscription URL is `https://preprod.registry.ondc.org/ondc/subscribe`, but an approved operator/Portal workflow—not application automation—must submit it. Production endpoints are forbidden without a new explicit authorization and review.

Official references:

- [ONDC participant onboarding](https://github.com/ONDC-Official/developer-docs/blob/main/registry/Onboarding%20of%20Participants.md)
- [ONDC signing and verification](https://github.com/ONDC-Official/developer-docs/blob/main/registry/signing-verification.md)
- [ONDC developer index and environment endpoints](https://github.com/ONDC-Official/.github/blob/main/profile/README.md)
- Pinned local Registry 2.1.0 contract: `backend/app/ondc/protocol/spec/registry-2.1.0.json`

Key rotation requires overlapping old/new key validity, deployed verification/challenge support, authorized Registry amendment, lookup confirmation and monitored cutover. The local generator never overwrites keys and operational rotation is not automated.
