# Current status — October 8, 2026

The audit below records the previous foundation stage. Its signing/discovery/publication persistence gaps are now implemented for local testing. Current results: **149 tests pass**, migrations at **0003**, existing admin smoke passes. See [ONDC_DISCOVERY.md](ONDC_DISCOVERY.md), [ONDC_SECURITY.md](ONDC_SECURITY.md) and [ONDC_VALIDATION.md](ONDC_VALIDATION.md) for the current implementation and verification limits.

# ONDC RET12 foundation gap analysis

Audited 2026-10-07 (America/New_York), before implementation. Existing SR Fashions application is retained.

## Existing application

| Area | Existing implementation | Integration gaps |
| --- | --- | --- |
| Seller | Integer ID, unique email, name, timestamps, store/product relationships | Network identity is separate; provider logo, business details, policies absent |
| Store | Seller ownership, name, free-text address, unique seller/name | GPS, structured address, pincode, serviceability, operating hours, publication status absent |
| Product | Seller ownership, name, brand, description, free-text category | Images, official RET12 category mapping, gender, fabric, size chart and other category-specific attributes absent |
| ProductVariant | Unique SKU, size, color, Decimal MRP/selling price; price constraints | Publication attribute mappings and identifiers need boundary validation |
| Inventory | Unique store/variant pair, bounded nonnegative quantity | No reservation, concurrent availability accounting, stock events or incremental catalog cursor |
| Order | Absent | Correlation IDs, order lifecycle, quotes, billing, idempotency |
| Fulfillment | Absent | Shipment/tracking, logistics relationships, fulfillment lifecycle |
| Payment | Absent | Collection, settlement, reconciliation and financial state |
| Return / cancellation | Absent | Requests, eligibility, refunds, cancellation terms and reason codes |

One Alembic migration (0001) creates the five existing business tables. No ONDC database tables exist. Existing FastAPI exposes seller/store/product/variant/inventory CRUD, root identity and database-backed health, constrained input schemas, CORS, sanitized 409/503 errors. Product creation commits product, variants and stock together. Existing tests cover CRUD, invalid stock/prices, rollback, ownership, duplicate email/SKU, health, CORS and absent protocol routes. Baseline: **17 passed**, one existing Starlette/httpx deprecation warning.

React has Dashboard, Add Product, Products and Inventory; orders, returns and ONDC settings are placeholders. API client uses only internal REST routes. Docker Compose uses PostgreSQL and an existing named volume. Launch scripts apply migrations and check app identity. Environment keys audited without printing credentials: root PostgreSQL configuration; backend DATABASE_URL/CORS_ORIGINS; frontend VITE_API_BASE_URL. Secrets are excluded by .gitignore; ONDC configuration must remain backend-only.

## Official source selection

The [official ONDC developer index](https://github.com/ONDC-Official/.github/blob/main/profile/README.md) lists **Retail B2C 1.2.5 (Latest)** and the developer guide branch **draft-b2c-1.2.5**. RET12 means Fashion; seller node type is ISN. The generic repository master README is primarily B2B/exports and the branch README still mentions 2.0.1: neither overrides the developer index and versioned API contract.

Pinned repository: [ONDC-RET-Specifications](https://github.com/ONDC-Official/ONDC-RET-Specifications/tree/7a9c7e6955018ae8f758c22f3f78f7af7d8def4e), build info.version 1.2.5. Official taxonomy: [Fashion (RET12)](https://docs.google.com/spreadsheets/d/1APAvavF_BNbTA89benAlGtv0GuFvpn2b6XXi4lSdTTw/edit#gid=623321892). Snapshot downloaded directly from the official sheet; preserve internal categories. T-Shirts is not the official T Shirts value; Kurtas is not Kurtas & Kurta Sets. No implicit category or attribute guessing is allowed.

## Planned isolated foundation

Implement lazy environment configuration, discovery/context and catalog Pydantic models, a pure ORM-to-catalog mapper with required external publication metadata, version-pinned references/taxonomy, ACK/NACK helpers and validators under backend/app/ondc/. Do not register routes or import ONDC settings during admin startup. No admin database migrations or frontend changes needed for this stage.

## Remaining integration work

Persist and administer accurate publication enrichment (images, geo/address, schedules, serviceability, attributes, statutory disclosures and policies); then signing and verification, registry lookup/key lifecycle, request authentication and replay protection, discovery routing and asynchronous callbacks, persistence/idempotency, catalog rejection framework, incremental refresh. Orders, quotes, inventory reservation, fulfillment, payments/settlement, cancellation, returns, reconciliation and observability require later development. Registry registration and PreProd access are outside this task.

## Verification boundaries

A pure mapper cannot make the current catalog publishable without the missing metadata. Test fixture metadata is synthetic and is not applied to live sellers. Protocol version suitability for actual onboarding must be reconfirmed before enabling network communication. This branch is explicitly named draft; local passing tests are not ONDC certification.

## Implemented foundation and final results

The planned isolated foundation is implemented. Configuration, schemas, mapper, official taxonomy/source snapshots, schema reconciliations and ACK/NACK helpers are present. Existing models, admin API, migrations, React and business data are preserved. Final automated results: **89 passed** (17 existing + 72 new). Live PostgreSQL smoke and HTTP health/frontend availability checks pass. See ONDC_VALIDATION.md for commands and file inventory and ONDC_SPECIFICATION.md for exact source decisions and supported-profile limits. No protocol routes, registry registration or PreProd access were performed.


## Discovery extension completed

| Previous gap | Current state |
| --- | --- |
| Persistent publication metadata | Seller/store/product side tables, opt-in provider flag and safe migrations; live records require real enrichment |
| Internal administration | Pydantic GET/PUT metadata APIs; secret inputs are not echoed; React remains intact |
| Signing and verification | Official Python-compatible Ed25519/BLAKE2b-512 implementation, development utility, gateway and buyer signatures |
| Replay protection | Unique database message key, exact-body conflict checks, multiworker leases and retention |
| Registry lookup | Signed, configurable, cached abstraction; mocked only |
| Outbound callbacks | Reusable asynchronous httpx client; signed gzip callbacks, timeout/HTTP/ACK failures, safe diagnostics |
| Discovery | /search ACK/NACK, validated durable catalog callback to buyer /on_search |
| Recovery | Persistent work, expired-lease recovery, failed retries, callback TTL stop, maintenance CLI |
| Local integration | Six-variant mock buyer test, real loopback HTTP, PostgreSQL migration/worker races; 149 passing tests |

Remaining: actual merchant enrichment; source ambiguities explicitly marked UNVERIFIED in security docs; wider catalog profiles, incremental refresh/disabled stores and rejection handling; admin authentication and deployment egress/observability; key lifecycle; all order/payment/fulfillment/return work. No onboarding or external network validation occurred. External communication defaults disabled.
