# SR Fashions - local foundation

FastAPI/PostgreSQL inventory backend and React retailer administration workspace.
Target future domain: **ONDC:RET12**. This is an internal retail application, not
an ONDC-compliant protocol implementation or a customer storefront.

A fresh clone needs one-time prerequisite and dependency installation before start.bat works.
See [SETUP.md](SETUP.md) for the steps, or copy the detailed
[Copilot local setup prompt](docs/COPILOT_LOCAL_SETUP_PROMPT.md) into Copilot Chat in Agent mode.

## Architecture

- `backend/app/main.py`: application, CORS, health, safe database error responses.
- `backend/app/config.py`, `database.py`: environment settings and SQLAlchemy sessions.
- `backend/app/models/`: Seller, Store, Product, ProductVariant, Inventory.
- `backend/app/schemas/`: Pydantic v2 inputs and outputs.
- `backend/app/api/`: internal REST endpoints.
- `backend/app/services/`: transactional catalog and ownership validation.
- `backend/app/ondc/{routes,schemas,signing,registry,catalog}/`: isolated local discovery, schemas, signing, lookup and catalog mapping.
- `backend/alembic/`: explicit, versioned database migrations.
- `backend/tests/`: isolated SQLite behavior tests with foreign keys enabled.
- `frontend/src/{api,components,pages,layouts}/`: admin SPA, shared Axios client.
- `docker-compose.yml`: PostgreSQL 17, loopback port binding, health check, durable volume.
- `scripts/`: safe environment initialization and live API smoke verification.

## Internal REST API

Open `http://127.0.0.1:8000/docs` for complete request and response schemas.

| Resource | Operations |
| --- | --- |
| `/`, `/health` | GET; health checks database connectivity |
| `/api/sellers` | GET list, POST |
| `/api/sellers/{id}` | GET, PUT, DELETE |
| `/api/stores` | GET list, POST |
| `/api/stores/{id}` | GET, PUT, DELETE |
| `/api/products` | GET list, POST with variants and optional initial stock |
| `/api/products/{id}` | GET, PUT product details, DELETE |
| `/api/products/{id}/variants/{variant_id}` | PUT variant details and prices |
| `/api/inventory` | GET list, POST |
| `/api/inventory/{id}` | GET, PUT quantity, DELETE |

Lists accept `offset` and `limit` (default 100, maximum 200); products/stores can
filter by `seller_id`, inventory by `store_id`. Frontend traverses all pages.
PUT replaces the fields described by the corresponding request schema. Seller
ownership of products and stores is immutable. SKU is globally unique for this
foundation. Prices use fixed-precision decimals; JSON responses serialize them
as strings. Admin prices are displayed in INR as a local application choice.

Product creation, variants, and opening stock are atomic. Inventory has one row
per store/variant, nonnegative integer quantity, and same-seller ownership checks.
Deleting products also deletes their variants/inventory. Sellers and stores with
dependent records cannot be deleted (409). Validation returns 422, absent resources
404, uniqueness/dependency conflicts 409, database unavailability 503.

## Scope and operational limits

Dashboard includes seller/store setup, catalog counts and stock totals. Products
supports search. Add Product creates one initial variant (API supports multiple).
Inventory supports store filtering and quantity editing. Orders, Returns and
ONDC Settings are explicit placeholders.

Local ONDC discovery, payload schemas, taxonomy mapping and signing are implemented.
External network communication defaults disabled; no Registry onboarding has occurred.
See [ONDC_DISCOVERY.md](docs/ONDC_DISCOVERY.md) for the supported profile and limits.
Category, color and size remain free-text internal fields with explicit publication mapping.

This local foundation has no authentication/authorization yet. Run it on loopback;
add access control before a shared deployment. Inventory uses absolute quantity
replacement, with last-write-wins behavior. It is not a reservation or order ledger.
Timestamps are UTC-aware on PostgreSQL; updates are maintained by SQLAlchemy.
No automatic schema creation runs at application startup; use Alembic.

`.env` files and virtual environments are ignored. Only the public API URL belongs
in `frontend/.env`; all `VITE_` values are public browser configuration. Random local
database credentials are generated outside source code. The source repository is [tnsurendra/sr-fashions-seller-platform](https://github.com/tnsurendra/sr-fashions-seller-platform).
No cloud deployment is configured.

Implementation references: [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/),
[SQLAlchemy relationships](https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html),
[Vite setup](https://vite.dev/guide/).
