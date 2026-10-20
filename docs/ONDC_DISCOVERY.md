
# Local RET12 discovery

Completed October 8, 2026. Supported profile: Retail B2C 1.2.5, ONDC:RET12, Seller, Inventory Seller Node. The existing FastAPI, React and PostgreSQL application is extended in place.

## Flow and boundaries

POST /search parses a bounded UTF-8 JSON entity, validates the existing strict context/discovery models and reconciled official schema, checks freshness, verifies sender/optional gateway identities and signatures, and applies persistent replay protection.

For a new request, the service reads the enabled seller, stores, products, variants, inventory and persisted enrichment. PostgreSQL discovery reads use a repeatable-read transaction. It maps and validates a complete callback before committing durable work and returning the protocol ACK. Prevalidation before ACK is a local implementation choice to reject an unusable catalog immediately; the catalog is never returned in the ACK.

FastAPI runs callback delivery after the response. A separate database session claims the committed record, revalidates its payload/TTL, signs it, and POSTs a gzip full catalog to the registered context.bap_uri base plus /on_search. transaction_id and message_id are preserved. The callback adds the configured seller identity/URL, uses the publication snapshot timestamp and configured city, and does not copy the inbound public encryption key.

Route, schema/freshness validation, authentication, service, mapper, durable replay state, Registry lookup and outbound client remain separate under backend/app/ondc/. Seller/admin CRUD behavior is retained. There is no inbound seller /on_search route: on_search is a callback to the buyer.

Full network searches must arrive through the gateway, per the current Retail contract. The direct mock-buyer path is permitted only in explicit local peer-test mode. Network readiness is not claimed.

## Publication persistence

Migration 0002 adds:

- ondc_seller_publication: one-to-one seller link, enabled flag default false, validated JSON provider metadata.
- ondc_store_publication: one-to-one store link, validated JSON GPS, structured address and operating/serviceability metadata.
- ondc_product_publication: one-to-one product link, validated JSON publication images, fashion attributes, color hex mappings, disclosures and policies.
- ondc_discovery_messages: unique inbound identity/correlation, exact-body fingerprint, accepted request, validated callback, destination, durable status, lease, attempt counter, retention time and safe failure token.

Migration 0003 adds a partial unique index so concurrent admin operations cannot enable two providers for this ISN. Existing rows and existing seller/store/product/variant/inventory columns are untouched; no catalog is enabled automatically. Side-table foreign keys preserve ownership and cascade metadata deletion with its parent.

Metadata reuses the previous PublicationProfile DTO and mapper. Database tables are independent from ONDC wire representations. JSON metadata was chosen to reuse those existing validated structures without duplicating product names, prices, SKUs or stock.

Required publication enrichment includes provider/seller logos/descriptions/contact, provider TTL, fulfillment type/contact; GPS, locality/street/city/state/pincode, hours, timing/serviceability tags; product images, exact official category mappings, category-specific attributes, country of origin, statutory disclosures, return/cancellation/COD/shipping policies, consumer care and maximum order count. Country is IND in context/configuration and origin_country in product disclosures; no unsupported location field is invented. Existing variant size/color/brand, Decimal prices and per-store stock stay authoritative.

Applicable discovery payment metadata covers finder-fee policy and item COD availability. Provider administration accepts optional finder_fee_policy with published finder_fee_type and finder_fee_amount_min/max terms as INTERNAL policy inputs, not extra catalog wire fields. Incoming fees must fit that explicit policy; no fee is silently accepted. Incoming bap_terms require an explicitly supplied accept_bap_terms=Y in bpp_terms. Actual static-contract review remains a merchant responsibility. Order payment/settlement structures are intentionally not implemented.

Supported discovery is one provider, configured city (or wildcard search), full refresh and existing category/name filters. Incremental refresh, buyer-location-filtered discovery and unsupported fulfillment requests are rejected. A query producing no supported inventory-backed items is NACKed under this nonempty full-catalog profile; generic empty/disabled-catalog support is deferred. Unknown fashion classifications have no guessed fallback.

## Internal metadata APIs

Use /docs locally to inspect full Pydantic schemas and submit real publication data:

| Method | Path | Purpose |
| --- | --- | --- |
| GET / PUT | /api/ondc/publication/sellers/{id} | Provider metadata, enabled status, fee policy |
| GET / PUT | /api/ondc/publication/stores/{id} | Location/address/GPS/timing/serviceability |
| GET / PUT | /api/ondc/publication/products/{id} | Product enrichment, attributes and policies |

PUT replaces that record's metadata. Missing owners return 404; invalid fields return sanitized 422. Store tags must reference store-{id}; provider mappings must resolve to exact official taxonomy. Final cross-record publication readiness is validated again by the existing mapper before ACK, so structurally valid but incomplete/mismatched enrichment cannot be sent.

No signing settings are exposed by these APIs. No React source changes were needed: internal administration is available through the existing FastAPI documentation. The React ONDC Settings page remains a placeholder; a dedicated form can be added later without redesigning the UI.

## Configuration

All variables are backend only. .env.example contains placeholders, not usable credentials.

| Variable | Meaning/default |
| --- | --- |
| ONDC_ENVIRONMENT | local; production rejected for this development scope |
| ONDC_DOMAIN / NETWORK_ROLE / NODE_TYPE / PROTOCOL_VERSION | ONDC:RET12 / Seller / ISN / 1.2.5 |
| ONDC_SUBSCRIBER_ID / SUBSCRIBER_URL | Seller hostname and protocol base URL |
| ONDC_CALLBACK_URL | Seller-side callback base; never replaces buyer bap_uri |
| ONDC_UNIQUE_KEY_ID / SIGNING_PRIVATE_KEY | Signing identity and protected base64 libsodium secret key |
| ONDC_COUNTRY / CITY | IND and explicit std city code |
| ONDC_ROUTE_PREFIX | Empty exposes /search; /ondc exposes /ondc/search; must match subscriber URL path |
| ONDC_REGISTRY_URL | Explicit local/mock signed v2.0 lookup endpoint |
| ONDC_HTTP_TIMEOUT | 5 seconds, positive and <=60 |
| ONDC_REGISTRY_CACHE_SECONDS | 60, range 0–300 |
| ONDC_REPLAY_RETENTION_SECONDS | 86400, minimum 3600 |
| ONDC_EXTERNAL_NETWORK_ENABLED | false; no external calls by default |
| ONDC_ALLOW_LOCAL_PEER_SEARCH | false; true permits no gateway signature only in local mode |
| ONDC_ALLOW_LOCAL_CALLBACKS | false; true permits local callback transport only in local mode |

The route prefix loads separately without requiring secrets. Restart the server after configuration changes; settings/service caches are process-local. Development key generation writes a protected, ignored environment file; load its contents securely into the process or backend .env yourself. It is not automatically merged into live configuration.

## Local automated testing

From backend:

    .\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short
    $env:ONDC_TEST_POSTGRES = '1'
    .\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short

The second command also verifies local PostgreSQL migrations and competing workers in a generated temporary schema. It removes only that schema; existing business records are not modified.

Focused end-to-end tests:

    .\.venv312\Scripts\python.exe -m pytest -q tests/test_ondc_discovery.py::test_signed_local_discovery_end_to_end
    .\.venv312\Scripts\python.exe -m pytest -q tests/test_ondc_discovery.py::test_real_loopback_http_discovery

tests/mock_buyer.py is development/test only. It generates signed searches, sends them to a seller client, receives /ondc/on_search, decompresses and verifies the seller signature, validates catalog/context, enforces transaction/message correlation and stores callbacks. Production application code does not import it.

The socket test starts seller and buyer servers on ephemeral loopback ports; Registry is mocked. It automatically creates an isolated SQLite catalog with SR Fashions / Main Store / Men's Cotton Shirt, black and white S/M/L SKUs, INR 1199 price / 1499 MRP, accurate fixture stock including zero, explicit brand/images/disclosures/policies, and proves ACK plus separately delivered signed callback. Those sample records are not inserted into the live merchant catalog.

Apply local migrations with:

    .\.venv312\Scripts\python.exe -m alembic upgrade head
    .\.venv312\Scripts\python.exe -m alembic check

To recover pending/failed work and clean delivered tombstones, schedule app.ondc.protocol.maintenance with the same protected local settings as the API. Expired callbacks stop automatically; start a fresh search with new IDs.

## Limits and next step

See ONDC_SECURITY.md for source conflicts, byte-identical retry policy, gzip signing-order ambiguity, live Registry/gateway behavior, DNS controls and secret handling. All external interoperability is UNVERIFIED; no onboarding was attempted.

Next, review accurate merchant metadata and resolve those official-source ambiguities, then add incremental catalog/store disabling and rejection handling before considering separately authorized PreProd verification. /select, /init, /confirm, /status, /cancel and /update remain unimplemented.
