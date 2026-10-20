
# ONDC discovery security

Completed October 8, 2026 (America/New_York). Scope: local Retail B2C 1.2.5, ONDC:RET12, Inventory Seller Node. No registration, subscription, PreProd or Production requests were made.

## Official sources and conflicts

The preserved Retail API contract's sections 2–3 specify asynchronous ACK/callback correlation, Ed25519, a Blake2b digest of UTF-8 JSON, signature verification, HTTP 401 for failed verification, and signed v2.0 Registry lookup. Existing source references remain in ONDC_SPECIFICATION.md.

Additional sources are snapshotted with SHA256 hashes in backend/app/ondc/protocol/spec/security-provenance.json:

- [Official Python signing utility](https://github.com/ONDC-Official/reference-implementations/blob/main/utilities/signing_and_verification/python/cryptic_utils.py).
- [ONDC signing/verification guide](https://github.com/ONDC-Official/developer-docs/blob/main/registry/signing-verification.md).
- [Registry onboarding/lookup documentation](https://github.com/ONDC-Official/developer-docs/blob/main/registry/Onboarding%20of%20Participants.md).
- [Registry OpenAPI 2.1.0](https://app.swaggerhub.com/apis/ONDC/ONDC-Registry-Onboarding/2.1.0).
- [Official ONIX v1.5.0 participant model](https://github.com/ONDC-Official/automation-beckn-onix/blob/v1.5.0/pkg/model/model.go), which enumerates BAP/BPP/BG roles.

The prose signing guide and onboarding curl examples omit spaces in some signed-header and signing-string examples. The official Python implementation consistently uses spaces after each colon and the signed-header list below. This implementation follows that executable reference. An automated test executes only its four signing helpers from the stored snapshot and proves bidirectional interoperability.

The Registry OpenAPI calls several lookup fields required, while the Retail contract and onboarding curl show fewer fields. The client sends subscriber_id, ukId, country, city, domain and type, satisfying both request examples and the stricter schema. OpenAPI's response omits some fields shown in the Retail contract (status, type and subscriber_url); verification requires those contract fields to avoid using an unbound or inactive key. Live response compatibility is UNVERIFIED. The developer index still lists Staging endpoints; the newer onboarding document marks Staging decommissioned. No Staging calls were made.

## Signing process

Private keys use base64 of the 64-byte libsodium secret key (32-byte seed followed by its corresponding 32-byte public key). Public keys use base64 of the raw 32-byte Ed25519 public key. Inconsistent private-key halves and malformed base64 fail closed.

1. Serialize JSON once using compact UTF-8, preserving non-ASCII characters and rejecting NaN/Infinity.
2. Hash the exact serialized JSON bytes with BLAKE2b, digest_size=64; base64 encode the digest. The wire label is BLAKE-512, despite the underlying algorithm being BLAKE2b.
3. Build exactly this string, with actual newlines:

    (created): <Unix integer>
    (expires): <Unix integer>
    digest: BLAKE-512=<base64 digest>

4. Sign its UTF-8 bytes with Ed25519, then base64 encode the 64-byte detached signature.
5. Send Authorization with keyId subscriber_id|unique_key_id|ed25519; algorithm ed25519; quoted integer created/expires; headers "(created) (expires) digest"; and signature.

There is no invented additional Digest HTTP header. The outbound client currently uses a 30-second signature lifetime as a local operational policy, not an ONDC-prescribed universal lifetime.

The current full-catalog contract requires Content-Encoding: gzip. The client signs the JSON bytes and then gzip-compresses them; the mock buyer decompresses before verifying those same bytes. The official sources describe UTF-8 JSON hashing and gzip separately; their ordering is an inference and **UNVERIFIED against an actual network receiver**. This is explicitly a local interoperability profile, not a certification claim.

## Verification process

Parse the Signature scheme strictly, reject missing/duplicate/unknown parameters, enforce Ed25519 in both algorithm locations, and validate the base64 signature length. Require created <= now < expires and created < expires. No positive clock-skew allowance is installed. The utility's inclusive expires comparison differs at the exact boundary; this implementation uses the prose requirement that expires remain in the future.

Look up the sender's exact subscriber/key/domain/country/city/role. Require SUBSCRIBED status and a currently valid key. Verify the exact received JSON bytes; do not parse and reserialize before hashing. Require the buyer subscriber ID to match context.bap_id and its registered URL to match context.bap_uri. Full network discovery requires both Authorization and X-Gateway-Authorization. A missing gateway signature is allowed only by the explicit local peer-search setting. Both signatures are verified when present, even in local peer mode.

Context timestamp must be timezone-aware, not in the future, and inside its positive search TTL (maximum PT30S in the existing foundation). Recheck TTL after catalog construction before persisting/ACKing. Stale requests use published Seller App code 30022. Invalid signatures/unknown subscribers use code 30016 and HTTP 401. Registry infrastructure failures use 31001 and HTTP 503. Invalid schemas use 30000; rejected fees use 41001; unaccepted buyer terms use 50005.

## Replay protection and callbacks

A database unique constraint covers (buyer subscriber, domain, action, transaction_id, message_id). It is independent of the signing key so key rotation cannot bypass deduplication. A SHA512 fingerprint of the exact request bytes detects changed bodies under reused IDs. SHA512 here is only a local storage fingerprint, not the ONDC wire digest.

Authenticated, still-fresh, byte-identical retries receive ACK and reuse the stored callback. Delivered work is not sent again. Changed bodies with the same key receive NACK 30022, including when a competing insert loses the database uniqueness race. Equivalent JSON with different bytes is treated as a conflicting retry; this conservative policy is local, not a published universal ONDC retry rule. New searches should use new message IDs.

The callback and destination are committed before ACK. Database compare-and-update leases arbitrate multiple workers; a worker holds the lease for HTTP timeout + 60 seconds. Another worker cannot claim that record while the lease is active. Expired leases allow recovery after a crash. Persistent statuses are pending, sending, failed, delivered and expired. Failed deliveries keep only a safe error token. Callback TTL expiry transitions to expired and prevents indefinite sending of an obsolete catalog.

HTTP delivery is at least once after an ambiguous timeout/crash: the receiver may have accepted a callback before its ACK was lost. Exactly-once delivery across HTTP is not claimed. Receivers must deduplicate by correlation IDs.

Default replay retention is 86400 seconds (local policy, minimum configurable 3600). Cleanup deletes delivered records past retain_until only. Pending/failed/expired records remain for investigation; operators must archive/delete terminal failures under their data-retention policy. Do not delete pending work indiscriminately. Run the maintenance command below to resume eligible work and prune delivered tombstones. It handles at most 100 callbacks per invocation; schedule repeated invocations as needed. No daemon or external queue is installed.

## Registry and outbound safety

Lookup uses signed POST to the configured URL; no production URL is installed as a default. Timeouts, HTTP failures, malformed JSON/records, duplicate matches and invalid public keys fail closed. Not-found, wrong-key, wrong-role, unsubscribed or expired records cannot authenticate a sender. Positive cache entries include identity/key/role/city, last at most 60 seconds by default, never outlive key validity, and are bounded to 512 entries. No negative caching is used. Cache is per process; replay protection is database backed.

The async httpx client disables environment proxies and redirects, checks HTTP status and validates callback ACK/NACK. Full payloads, Authorization values and customer information are not logged. Diagnostics contain only safe status/error tokens and internal discovery record IDs. Outbound callbacks are revalidated before sending.

External HTTP is disabled by default; local loopback and injected test transports remain usable. Production configuration and the production Registry hostname are rejected. Callback destinations must equal the registered buyer URL, use HTTPS outside an explicit local exception, and resolve to public addresses. These checks do not establish DNS-rebinding protection across separate resolution/connect operations; deployment egress restrictions or a pinned-resolution transport remain required before enabling external communication. Live gateway Registry scoping (domain/city) is UNVERIFIED.

## Administration and secrets

Publication APIs persist only validated metadata; no key settings appear in request/response models or React. Rejected publication inputs are not echoed in 422 responses. Signing configuration loads lazily, as SecretStr excluded from dumps/repr. Startup and existing admin operations do not require ONDC credentials.

Generate development material from backend:

    .\.venv312\Scripts\python.exe -m app.ondc.signing.generate

This writes .ondc-keys/.env without printing private keys and refuses to overwrite an existing file. That directory and environment files are gitignored. Secure its Windows ACL or use a secret manager; file mode 0600 alone does not establish Windows ACL protection. No persistent development private key has been added to this repository or its live environment by this task. Tests use ephemeral generated keys.

The existing administration APIs have no user authentication/authorization. Keep them internal; adding production admin authentication is an existing application gap, outside this discovery implementation.

Recovery/cleanup, from backend with protected local configuration loaded:

    .\.venv312\Scripts\python.exe -m app.ondc.protocol.maintenance

Do not enable external communication or real credentials until the listed network ambiguities and deployment controls have been reviewed.
