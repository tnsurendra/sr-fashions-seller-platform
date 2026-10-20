# Validation results

Performed October 7, 2026 (America/New_York).

- [PASS] Python 3.12.10 x64 installed; backend dependencies installed in `backend/.venv312`.
- [PASS] Node.js 24.19.0, Git, Docker Desktop, and WSL installed.
- [PASS] Git initialized on `main`; no remote configured and no commit created.
- [PASS] Root/backend/frontend `.env` files and virtual environments excluded by Git.
- [PASS] Docker Compose configuration validated.
- [PASS] PostgreSQL 17.11 container started and healthy; database `ondc_fashion`.
- [PASS] Alembic `upgrade head` applied successfully.
- [PASS] Alembic `current` reports `0001 (head)`.
- [PASS] Alembic `check` reports no new upgrade operations (no schema drift).
- [PASS] FastAPI started on `127.0.0.1:8000`.
- [PASS] Live `GET /health`: HTTP 200, `{"status":"ok","database":"ok"}`.
- [PASS] PostgreSQL-backed smoke test: create seller/store/product/variant/stock,
  read product, update inventory, reject duplicate SKU, and clean up its temporary records.
- [PASS] Pytest: **17 passed**, using isolated SQLite databases with foreign keys enabled.
- [PASS] React production build: Vite 7.3.7, 103 modules transformed.
- [PASS] npm install audit reported zero vulnerabilities.
- [PASS] Vite development server started on `127.0.0.1:5173`.
- [PASS] ONDC boundary directories created; no protocol routes, signing, registry
  onboarding, network taxonomy, or private keys implemented.
- [FAIL] No unresolved implementation/build/test failure.
- [MANUAL] Visual/browser interaction testing remains unverified: the browser runtime
  reported no connected browsers. Open the admin URL and exercise seller/store setup,
  Add Product, Products, and Inventory.

## Errors encountered and resolved

1. ARM64 Python lacked a psycopg binary wheel. Installed x64 Python 3.12 and used
   `.venv312`; the unused `.venv` remains ignored and was not deleted.
2. WSL installation required administrator privileges. Elevated installation succeeded;
   Docker started successfully without a Windows restart in this session.
3. Docker could not find its credential helper in the old shell PATH. Added Docker's
   installed binary directory to the command environment; PostgreSQL image pull succeeded.
4. PostgreSQL connection using `localhost` stalled. Switched to explicit IPv4
   (`127.0.0.1`) and added a bounded connection timeout; migrations and live CRUD passed.
5. An oversized Windows file-creation command failed before execution. Split the writes;
   all requested source files were created successfully.

## Non-failing warning

The installed Starlette TestClient emits a deprecation warning about its `httpx`
transport in favor of `httpx2`. All tests pass using the requested `httpx` stack.
The exact working backend dependency versions are recorded in `requirements.lock.txt`.

Backend and frontend processes were left running at completion; the Docker database
also remains running. If a terminal/session ends, restart using SETUP.md. The database
contains no smoke-test records. No browser end-to-end success is claimed.
