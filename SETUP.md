# Setup and operation

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

- Python 3.12+; on this Windows ARM machine use installed **x64 Python 3.12** for
  the psycopg binary wheel. ARM64 Python 3.13 could not install that wheel.
- Node.js LTS (installed 24.19.0), npm, Git.
- Docker Desktop with Linux containers and WSL2 running on Windows.
- Free local ports 5432, 8000, 5173.

Open a new PowerShell after installing tools so PATH includes Node, Docker and Git.
Commands below start at `C:\Users\Surendra\Fashion-Seller\sr-fashionns`.
Use `npm.cmd` on Windows to avoid PowerShell script execution-policy issues.

## Environment

Local `.env`, `backend/.env`, and `frontend/.env` were created automatically for
this workspace. Do not overwrite them with examples.

For a fresh checkout only:

```powershell
python .\scripts\init_env.py
```

The script generates one random password consistently for Compose and the backend,
and refuses to overwrite any existing environment files. Review `.env.example`
files for configuration keys; example passwords are placeholders. For external
credentials, URL-encode the password in DATABASE_URL. If changing the database
port, update both root `.env` and backend DATABASE_URL. PostgreSQL initializes
credentials only for an empty volume; changing `.env` does not rotate an existing
role password. Preserve the volume and rotate via PostgreSQL if necessary.

## Install dependencies (already completed in this workspace)

```powershell
cd C:\Users\Surendra\Fashion-Seller\sr-fashionns\backend
& "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe" -m venv .venv312
.\.venv312\Scripts\python.exe -m pip install -r requirements.lock.txt
cd ..\frontend
npm.cmd ci
```

For other operating systems or Python versions, create a normal virtual environment
and install `requirements.txt`; `requirements.lock.txt` records this verified Python
3.12 Windows environment. `package-lock.json` records frontend versions.

## Start database and apply migrations

```powershell
cd C:\Users\Surendra\Fashion-Seller\sr-fashionns
docker compose up -d --wait
cd backend
.\.venv312\Scripts\python.exe -m alembic upgrade head
.\.venv312\Scripts\python.exe -m alembic current
.\.venv312\Scripts\python.exe -m alembic check
```

## Start backend (terminal 1)

```powershell
cd C:\Users\Surendra\Fashion-Seller\sr-fashionns\backend
.\.venv312\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Start frontend (terminal 2)

```powershell
cd C:\Users\Surendra\Fashion-Seller\sr-fashionns\frontend
npm.cmd run dev
```

Open http://127.0.0.1:5173. On Dashboard, create a seller profile, then its store.
Choose Add Product, enter details and opening stock, and save. Products lists the
new variant. Inventory lets you filter by store and update stock.
Swagger documentation: http://127.0.0.1:8000/docs.

## Verify

```powershell
cd C:\Users\Surendra\Fashion-Seller\sr-fashionns\backend
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

Five catalog products are available under seller 2 and store 2, with six variants
and 85 initial units. Product IDs: 3 (shirt), 4 (jeans), 5 (kurta), 6 (T-shirt),
7 (hoodie). The hoodie starts out of stock. Categories are internal labels.

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

## Complete the project folder rename

If Windows locks `ondc-fashion-seller`, stop both app servers and close the IDE.
From a separate PowerShell outside the project folder, run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\Surendra\Fashion-Seller\rename-to-sr-fashionns.ps1
```

Reopen `C:\Users\Surendra\Fashion-Seller\sr-fashionns`. Compose retains its
existing project identity so the PostgreSQL volume and catalog remain available.
