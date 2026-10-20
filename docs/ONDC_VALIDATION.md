
# ONDC signed discovery validation and final report

Completed October 8, 2026 (America/New_York). This is a local development result, not ONDC network certification. The preceding foundation stage passed 89 tests; it remains the baseline for this extension.

## 1. Baseline test result

Before code edits, the complete existing suite passed **89 tests**, zero failures. The original audit/reference snapshots were inspected and preserved. The same pre-existing Starlette/httpx TestClient deprecation warning was present before this task.

## 2. Files created

- backend/app/ondc/models.py
- backend/app/ondc/catalog/administration.py
- backend/app/ondc/catalog/discovery.py
- backend/app/ondc/clients/http.py
- backend/app/ondc/registry/client.py
- backend/app/ondc/routes/discovery.py
- backend/app/ondc/signing/crypto.py
- backend/app/ondc/signing/security.py
- backend/app/ondc/signing/generate.py
- backend/app/ondc/protocol/replay.py
- backend/app/ondc/protocol/service.py
- backend/app/ondc/protocol/maintenance.py
- backend/app/ondc/protocol/errors.py
- backend/alembic/versions/0002_ondc_publication_discovery.py
- backend/alembic/versions/0003_ondc_provider_uniqueness.py
- backend/tests/mock_buyer.py
- backend/tests/test_ondc_discovery.py
- backend/tests/test_ondc_migrations.py
- backend/app/ondc/protocol/spec/signing-reference.py.txt
- backend/app/ondc/protocol/spec/signing-verification.md
- backend/app/ondc/protocol/spec/registry-onboarding-reference.md
- backend/app/ondc/protocol/spec/registry-2.1.0.json
- backend/app/ondc/protocol/spec/onix-model-v1.5.0.go.txt
- backend/app/ondc/protocol/spec/security-provenance.json
- docs/ONDC_SECURITY.md
- docs/ONDC_DISCOVERY.md

## 3. Files modified

- .gitignore
- backend/.env.example
- backend/requirements.txt
- backend/requirements.lock.txt
- backend/app/main.py
- backend/alembic/env.py
- backend/app/ondc/config/__init__.py
- backend/app/ondc/catalog/publication.py
- backend/app/ondc/README.md
- backend/tests/test_api.py
- backend/tests/test_ondc_foundation.py
- docs/ONDC_SPECIFICATION.md
- docs/ONDC_GAP_ANALYSIS.md
- docs/ONDC_VALIDATION.md

No existing business ORM tables, seller/admin routes, frontend source or real environment credentials were rewritten.

## 4. Database migrations

PASS: local PostgreSQL is at **0003 (head)**. Migration 0002 adds seller/store/product publication side tables and durable discovery messages. Migration 0003 adds the partial unique enabled-provider index. Metadata defaults unpublished; pre-existing rows retain their values.

PASS: SQLite upgrade/downgrade preservation tests and actual PostgreSQL upgrade/downgrade/re-upgrade tests in a generated temporary schema. PostgreSQL competing inserts resolve to one replay record; competing callback leases produce exactly one claimant. The temporary schema is removed. PASS: alembic check reports no new upgrade operations.

## 5. Publication metadata implemented

PASS: provider logos/descriptions/contact, store GPS/structured address/operating/serviceability tags, product images/exact taxonomy mapping/fashion attributes/color metadata/origin/disclosures/policies, configured fulfillment and optional fee policy persist through validated internal GET/PUT APIs. Existing variants/prices/inventory remain authoritative. Final mapper validation prevents incomplete enrichment from being sent. No live merchant metadata or sample catalog was installed automatically.

## 6. Cryptography implemented

PASS: libsodium/PyNaCl Ed25519, raw base64 64-byte private / 32-byte public keys, BLAKE2b-512 body digest, exact reference signing string, detached base64 signature, Authorization creation/parsing, exact-body verification and integer validity windows. Automated interoperability runs the official Python snapshot's signing helpers in both directions. Development key generation refuses overwrite and does not print private keys.

## 7. Replay protection design

PASS: database uniqueness on sender/domain/action/transaction/message, exact-body fingerprint, identical authenticated retry ACK, changed-body NACK 30022, durable callback record before ACK, multiworker delivery leases, failure recovery and terminal expiry. Default retention is one day; maintenance prunes only expired delivered tombstones. Failed/expired work requires operator retention handling. Ambiguous HTTP failures can cause repeat callback delivery; exactly-once HTTP is not claimed.

## 8. Registry client design

PASS: configurable signed v2.0 lookup, exact subscriber/key/role/domain/country/city/status/validity binding, bounded positive cache, timeout/HTTP/malformed/not-found handling. All Registry tests use mocks. No Registry subscription or live lookup was performed.

## 9. /search implementation

PASS: POST /search by default, or configured prefix + /search matching subscriber URL. Bounded entity parsing, strict schema/context, signatures, clock/TTL, gateway verification, publication validation, replay claim and ACK/NACK. No catalog is returned in ACK. Invalid signatures use HTTP 401 / Seller code 30016. Other errors use the pinned official Seller App list.

## 10. /on_search implementation

PASS: asynchronous outbound callback to registered buyer bap_uri + /on_search; mapper uses persisted metadata and current ORM catalog, preserves transaction/message IDs, validates before ACK and again before dispatch, signs and sends gzip JSON. Timeouts, HTTP errors, invalid ACK/NACK and callback expiry persist safe status. Recovery uses a separate session and lease. There is no inbound seller /on_search endpoint.

## 11. Mock buyer test result

PASS: in-process and actual loopback HTTP discovery. The mock buyer signs search, receives ACK, receives and decompresses callback, verifies seller signature, validates RET12 payload and checks exact correlation. Realistic fixture: SR Fashions / Main Store / Men's Cotton Shirt, BLACK/WHITE S/M/L (six SKUs), INR 1199 / 1499, brand/images/attributes/disclosures and stock including zero.

## 12. Security test results

PASS: missing/malformed/duplicate Authorization fields, invalid algorithms/signatures, unknown or invalid Registry keys, expired/future signature windows, altered body, identity/URI mismatch, invalid/future/expired context, unsupported domain, absent TTL, invalid/duplicate JSON, body reuse under identical IDs, missing/invalid gateway signature, invalid catalog, Registry timeout/HTTP/malformed response, callback timeout/HTTP/NACK/malformed response, callback expiry/recovery, private destination rejection, production/external network guards, invalid metadata/taxonomy, rejected secret input sanitization and development-key output handling.

## 13. Total test count

**149 passed, 0 failures, 0 skipped** when local PostgreSQL verification is enabled: original 89 plus 60 additional tests. Without ONDC_TEST_POSTGRES=1, the optional PostgreSQL test is skipped (148 pass, 1 skip).

Command, from backend:

    $env:ONDC_TEST_POSTGRES = '1'
    .\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short

Focused socket discovery and migration test runs also passed. No frontend changes were made, so a React production build was not required or claimed.

## 14. Regressions

PASS: complete seller/admin tests, PostgreSQL-backed live CRUD smoke (health, product creation/read, inventory edit, duplicate SKU rejection). Temporary smoke records were removed. Existing backend health and React development page remain available. Existing business data was preserved.

Two previous tests expected /search to be absent; their assertions were updated for this explicitly authorized endpoint. All deferred routes still return 404. The pre-existing Starlette TestClient deprecation warning remains non-failing.

## 15. Official ONDC sources used

Retail B2C **1.2.5** remains listed as Latest by the [official developer index](https://github.com/ONDC-Official/.github/blob/main/profile/README.md). The preserved [1.2.5 API contract](https://docs.google.com/document/d/1E2OyVXh34YNEVOnS4rO3nPVoqTO3RsG2uh-BqnSrqgY), pinned schema/error codes and official RET12 taxonomy remain in use. Signing/lookup sources and SHA256 snapshots are listed in ONDC_SECURITY.md and security-provenance.json. The original provenance.json and foundation snapshots were not replaced.

## 16. Unresolved specification questions

**UNVERIFIED:** actual receiver compatibility for hashing decompressed JSON with gzip transport; live Registry field/role/city behavior and gateway record scoping; current onboarding-environment acceptance; real city/pincode membership and geographic serviceability.

Documented source conflicts: signing whitespace examples versus executable utility; Registry minimal examples versus OpenAPI required fields/response omissions; Staging endpoint listing versus decommissioning notice. Previous schema/contract conflicts remain documented in ONDC_SPECIFICATION.md. Local strictness/retry retention/lease settings are explicitly local policies, not invented ONDC mandates.

## 17. Remaining ONDC gaps

Incremental refresh, disabled store/provider publication, catalog rejection handling, wider valid discovery profiles, enhanced serviceability geometry, static-term governance and actual merchant enrichment. Before external use: authentication for the existing internal admin APIs, DNS/egress hardening, key lifecycle/rotation, scheduled durable recovery/retention and operational observability. Orders/quotes/reservations/fulfillment/payment settlement/returns/cancellations remain absent.

## 18. Manual actions required

For manual local discovery only: supply protected development signing material and matching subscriber/base/prefix/city; provide a local mock Registry/buyer; maintain accurate publication metadata through /docs; enable one provider and explicit local test exceptions where needed; schedule the maintenance command for callback recovery/cleanup. Automated discovery tests need none of these live configuration changes.

Do not use synthetic fixture policies as merchant promises. No generated private key, real credentials, registration, Portal request, PreProd connection or Production connection was created by this task.

## 19. Recommended next step

Resolve the UNVERIFIED interoperability items against updated official guidance, review real merchant metadata, then implement incremental catalog/store-disable and rejection workflows. Consider external verification only as a separately authorized step; do not proceed into ordering endpoints yet.
