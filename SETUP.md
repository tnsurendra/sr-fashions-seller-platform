# Setup and operation

## Fresh-clone prerequisite setup

**start.bat starts configured services; it does not install prerequisites or dependencies.**
A fresh clone must complete the one-time steps below first. Git does not include local
.env files, Python virtual environments, node_modules, database volumes or business data.

For agent-assisted installation, copy the detailed [Copilot local setup prompt](docs/COPILOT_LOCAL_SETUP_PROMPT.md)
into Copilot Chat in Agent mode. It covers prerequisite installation, architecture checks,
Docker/WSL2, configuration, startup, verification and troubleshooting.

## First-run checklist

- [ ] Git, Python 3.12 x64, Node/npm and Docker Desktop are installed.
- [ ] WSL2 and Docker's Linux-container engine are ready.
- [ ] Root, backend and frontend .env files contain matching local configuration.
- [ ] Backend dependencies are installed in backend/.venv312.
- [ ] Frontend dependencies are installed using npm.cmd ci.
- [ ] Ports 5432, 8000 and 5173 are available or used by the healthy matching app.
- [ ] Run start.bat and verify backend health plus the admin page.

The [Copilot setup prompt](docs/COPILOT_LOCAL_SETUP_PROMPT.md) walks through each item,
including installation and troubleshooting. After setup, future starts need only start.bat.

## One-click Windows startup

Double-click **start.bat** in the project folder, or run ` .\start.bat` from
PowerShell. It starts Docker Desktop if needed, waits for PostgreSQL, applies
Alembic migrations, and starts the backend and frontend in separate terminals.
Open http://127.0.0.1:5173 when the launcher reports ready.

Existing healthy app servers are reused. Occupied ports with an unexpected or
unhealthy service produce an error instead of terminating that process. Existing
data and environment files are preserved. Initial dependency installation must
be completed first using the instructions below.

The launcher resolves paths relative to itself, so it works after a folder rename.
Close app servers using Ctrl+C in their windows; run `docker compose stop` from
the project folder to stop PostgreSQL without removing its data.
For unattended invocation, `start.bat --no-pause` returns an exit code without
waiting for a keypress. Startup errors remain visible in the launcher window.


## Prerequisites

- Python **3.12 x64** for the tested Windows environment; use x64 Python on Windows ARM for
  the psycopg binary wheel. ARM64 Python 3.13 could not install that wheel.
- Node.js **24 LTS** (or a verified compatible release), npm and Git for Windows.
- Docker Desktop with Linux containers and WSL2 running on Windows.
- Free local ports 5432, 8000, 5173.

Open a new PowerShell after installing tools so PATH includes Node, Docker and Git.
Replace the placeholder checkout path with your actual directory. Commands below start at `C:\path\to\sr-fashions-seller-platform`.
Use `npm.cmd` on Windows to avoid PowerShell script execution-policy issues.

## Environment

Local .env files must be created separately on each computer. Preserve any existing
configuration; do not overwrite it with placeholder examples.

For a fresh checkout only:

```powershell
py -3.12 .\scripts\init_env.py
```

The script generates one random password consistently for Compose and the backend,
and refuses to overwrite any existing environment files. Review `.env.example`
files for configuration keys; example passwords are placeholders. For external
credentials, URL-encode the password in DATABASE_URL. If changing the database
port, update both root `.env` and backend DATABASE_URL. PostgreSQL initializes
credentials only for an empty volume; changing `.env` does not rotate an existing
role password. Preserve the volume and rotate via PostgreSQL if necessary.

## Install dependencies once on each machine

```powershell
cd C:\path\to\sr-fashions-seller-platform\backend
py -3.12 -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements.lock.txt
cd ..\frontend
npm.cmd ci
```

Verify the selected interpreter architecture before creating the environment. On a
machine with several Python installations, invoke the verified x64 Python 3.12 executable
explicitly if the launcher selects a different architecture.

For other operating systems or Python versions, create a normal virtual environment
and install `requirements.txt`; `requirements.lock.txt` records this verified Python
3.12 Windows environment. `package-lock.json` records frontend versions.

## Start database and apply migrations

```powershell
cd C:\path\to\sr-fashions-seller-platform
docker compose up -d --wait
cd backend
.\.venv312\Scripts\python.exe -m alembic upgrade head
.\.venv312\Scripts\python.exe -m alembic current
.\.venv312\Scripts\python.exe -m alembic check
```

## Start backend (terminal 1)

```powershell
cd C:\path\to\sr-fashions-seller-platform\backend
.\.venv312\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Start frontend (terminal 2)

```powershell
cd C:\path\to\sr-fashions-seller-platform\frontend
npm.cmd run dev
```

Open http://127.0.0.1:5173. On Dashboard, create a seller profile, then its store.
Choose Add Product, enter details and opening stock, and save. Products lists the
new variant. Inventory lets you filter by store and update stock.
Swagger documentation: http://127.0.0.1:8000/docs.

## Verify

```powershell
cd C:\path\to\sr-fashions-seller-platform\backend
.\.venv312\Scripts\python.exe -m pytest -q
.\.venv312\Scripts\python.exe ..\scripts\smoke.py
Invoke-RestMethod http://127.0.0.1:8000/health
cd ..\frontend
npm.cmd run build
```

Expected health: `{"status":"ok","database":"ok"}`. The tests use isolated
in-memory SQLite databases with foreign keys enabled; they do not establish
PostgreSQL availability. The smoke script requires the migrated PostgreSQL-backed
server and creates then removes its own temporary records. A 503 health response
means the database is unavailable, even if the FastAPI process itself has started.

`npm.cmd run preview -- --port 5173` serves the production build locally when the
dev server is stopped. Vite's default preview port 4173 is not in backend CORS;
use 5173 or explicitly add its origin to CORS_ORIGINS and restart the backend.

## New migrations

```powershell
cd backend
.\.venv312\Scripts\python.exe -m alembic revision --autogenerate -m "describe change"
# Review the generated migration before applying it.
.\.venv312\Scripts\python.exe -m alembic upgrade head
```

## Stop

Ctrl+C in both server terminals. From the project root, `docker compose stop` stops
PostgreSQL while preserving data. `docker compose down` also preserves the named
volume. Do not add `-v` unless intentionally deleting database data.

## Troubleshooting

- Docker daemon unavailable: start Docker Desktop and wait for its Linux engine.
- On Windows ARM, install WSL as administrator if required:
  `winget install --id Microsoft.WSL --exact`. Restart Windows if prompted, then
  start Docker Desktop again. No automatic reboot is performed by this project.
- `docker-credential-desktop` not found: reopen PowerShell or add
  `C:\Program Files\Docker\Docker\resources\bin` to PATH.
- `npm` or `git` not found after installation: reopen PowerShell.
- Duplicate email/SKU or occupied store/variant pair: change the value or update
  the existing record. Seller/store deletions with dependencies return 409.
- This machine stalled on the PostgreSQL `localhost` connection; environment examples use
  `127.0.0.1`, and backend connections have a five-second timeout.
- Connection refused: ensure PostgreSQL is healthy (`docker compose ps`) and ports
  match the environment files. Never paste database URLs containing passwords
  into logs or support messages.

See VALIDATION.md for the exact checks performed in this workspace.

## Catalog products and Postman

A fresh database is empty: the original merchant records and PostgreSQL volume are
not included in Git. Create a seller/store and products through the UI, or explicitly
opt in to the sample catalog below. Sample IDs differ between computers.

To seed a fresh running instance, from the project root run:

```powershell
.\backend\.venv312\Scripts\python.exe .\scripts\seed_catalog.py
```

Existing catalog SKUs are skipped and stock is not reset. IDs above refer to this
workspace; a fresh database may assign different IDs.

Import `postman/SR-Fashions.postman_collection.json` in Postman. Its
`base_url` variable defaults to `http://127.0.0.1:8000`. IDs match this workspace.
GET requests read data; POST/PUT requests modify catalog data when sent. The create
request uses Postman's timestamp variable in the SKU to avoid ordinary duplicate
submissions. Duplicate SKUs return 409. No authentication is configured locally.


## Current ONDC discovery and tests

Ordinary seller/admin startup needs no ONDC signing key or Registry access. Local
network-discovery setup is separate: see [ONDC_DISCOVERY.md](docs/ONDC_DISCOVERY.md).
Do not perform onboarding as part of prerequisite installation.

Run tests from the backend directory. At this revision the default suite has 148
passing tests and one optional PostgreSQL test skipped. ONDC_TEST_POSTGRES=1 enables
the isolated PostgreSQL migration/worker test (previously 149 total passing tests).
See [ONDC_VALIDATION.md](docs/ONDC_VALIDATION.md) for verification boundaries.

For the complete install-and-run agent instructions, use
[COPILOT_LOCAL_SETUP_PROMPT.md](docs/COPILOT_LOCAL_SETUP_PROMPT.md).
