# Copilot prompt: install prerequisites and run SR Fashions

Copy the prompt below into GitHub Copilot Chat in **Agent mode** on the target Windows computer. Open the cloned repository as the workspace first. Copilot needs terminal access to perform the checks and installations. Installation may require Windows administrator approval, a reboot, or manual Docker Desktop setup.

A fresh clone does **not** run by double-clicking start.bat immediately. The launcher starts configured services; it does not install prerequisites, dependencies or environment files.

## Copy this complete prompt

---

Set up and run the EXISTING SR Fashions seller platform on this computer.

Repository: https://github.com/tnsurendra/sr-fashions-seller-platform

Do not recreate the application. Inspect it, install missing prerequisites, configure local development, install dependencies, run migrations, start the application and verify it. Continue through ordinary recoverable errors. Do not merely give me a list of commands if you can execute the authorized local setup yourself.

### 1. Inspect and plan from the actual checkout

Read these files before changing anything:

- Any applicable AGENTS.md.
- start.bat and scripts/start-dev.ps1.
- SETUP.md and README.md.
- scripts/init_env.py.
- docker-compose.yml.
- backend/requirements.lock.txt and backend/requirements.txt.
- frontend/package.json and frontend/package-lock.json.
- Root, backend and frontend .env.example files.
- docs/ONDC_DISCOVERY.md and docs/ONDC_SECURITY.md.

Check Git status and preserve any existing changes. Resolve the repository path from the current workspace; do not use the original author's username or absolute filesystem paths.

Explain the detected operating system, CPU architecture, installed tool versions, missing prerequisites and installation steps. This launcher is for native Windows. If this is Linux/macOS or an editor connected to WSL, explain the mismatch and use appropriate manual service commands rather than claiming start.bat runs there.

### 2. Preserve data and keep this setup local

- Keep existing database volumes, environment files, business records and user changes.
- Do not run docker compose down -v, delete a database volume, reset Git, or reinstall working software unnecessarily.
- Do not display passwords, private keys, complete DATABASE_URL values, or environment-file contents in logs or the final report.
- Never place database/signing secrets in frontend configuration. VITE_ variables are public.
- Do not disable antivirus, firewall, UAC or machine-wide execution policies to make setup work.
- Do not make registry subscriptions, ONDC Portal requests, PreProd/Production calls or real signing-key configuration. Ordinary seller/admin startup does not require ONDC credentials.
- Do not automate account login, license acceptance, BIOS changes or reboot. Tell me the precise manual action when one is necessary and resume after I complete it.
- Use official vendors/Microsoft WinGet sources. Verify package identity and architecture before installation. Do not pipe remote installation scripts into a shell.
- Check each external command's exit code; PowerShell's ErrorActionPreference alone does not detect every native-command failure.

### 3. Diagnose the Windows prerequisites

Run read-only checks first, adapting gracefully when a command is absent:

    Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture
    Get-CimInstance Win32_Processor | Select-Object Name, AddressWidth, VirtualizationFirmwareEnabled
    winget --version
    git --version
    py -0p
    node --version
    npm.cmd --version
    wsl --status
    wsl --version
    docker --version
    docker compose version
    docker info

Target this project's tested Windows development configuration:

- Git for Windows.
- Python **3.12 x64**, with the Python launcher available. The launcher expects backend\.venv312\Scripts\python.exe.
- Node.js **24 LTS** and its bundled npm; a compatible existing installation can be retained. Vite 7 requires a sufficiently recent Node release; inspect package engine requirements rather than using an old Node 18 installation.
- Docker Desktop, running Linux containers with WSL2.
- Hardware virtualization enabled and a Windows version supported by the currently installed Docker Desktop.
- Free local ports 5432, 8000 and 5173.
- Internet access for initial downloads from official package registries and Docker Hub.
- An account with access to the GitHub repository if it is private. Existing local access is enough; do not request a personal access token in chat.

For Windows ARM64, do not blindly select ARM64 Python: this project was tested with x64 Python 3.12 and binary dependency wheels. Check the interpreter's architecture and the vendor's current support. Use the architecture-appropriate Docker Desktop installer; do not install an x64-only Docker build on an unsupported ARM system.

Do not hard-code an outdated Docker RAM/build requirement: check the current official Docker Windows requirements and report whether this computer meets them.

### 4. Install only missing prerequisites

Use winget show to verify availability first. These are expected package identities, not a reason to replace an already working installation:

    winget show --id Git.Git --exact --source winget
    winget show --id Python.Python.3.12 --exact --source winget
    winget show --id OpenJS.NodeJS.LTS --exact --source winget
    winget show --id Docker.DockerDesktop --exact --source winget

Where installation is needed, run the corresponding command:

    winget install --id Git.Git --exact --source winget
    winget install --id Python.Python.3.12 --exact --source winget --architecture x64
    winget install --id OpenJS.NodeJS.LTS --exact --source winget
    winget install --id Docker.DockerDesktop --exact --source winget

Verify which Node major the LTS package supplies at execution time. Prefer the tested Node 24 LTS when choosing a new installation; if the package now points to a newer major, check compatibility or obtain Node 24 from the official Node.js download page. Do not downgrade a compatible existing Node installation merely to match this example.

If WinGet is missing, explain how to install/update Microsoft's App Installer through the supported Microsoft channel. If the device is managed, identify the policy restriction and the IT/manual step rather than attempting to bypass it.

If WSL is missing, show the required administrator command and explain the restart requirement:

    wsl --install --no-distribution

Follow current Microsoft/Docker guidance if that option is unavailable. After the user completes any required restart:

    wsl --update
    wsl --status
    wsl --version

Do not install a separate PostgreSQL Windows service: docker-compose.yml already provides PostgreSQL 17. Do not require a separately installed Ubuntu distribution unless the actual Docker/WSL setup requires it.

Ask the user to open Docker Desktop once to complete any first-run interaction. Confirm the Linux engine is running with docker info. Do not treat the Docker CLI's presence as proof that its engine is ready.

After installations, reopen the terminal or refresh PATH for this process using the user's existing machine/user PATH values. Do not overwrite persistent PATH. Verify Git, Python, Node/npm, Docker and Compose again.

### 5. Locate or clone the repository

If already inside the intended checkout, use it and do not clone a second copy. Otherwise, after Git is installed:

    git clone https://github.com/tnsurendra/sr-fashions-seller-platform.git
    Set-Location -LiteralPath .\sr-fashions-seller-platform

Use the user's chosen parent directory; never assume C:\Users\Surendra exists.

For a private repository, let the user complete normal GitHub authentication when prompted. Do not extract Chrome cookies or probe unrelated stored credentials.

From the project root:

    $projectRoot = (Get-Location).Path
    Test-Path -LiteralPath .\start.bat
    Test-Path -LiteralPath .\backend\requirements.lock.txt
    Test-Path -LiteralPath .\frontend\package-lock.json

If this is an existing checkout, do not automatically pull over uncommitted work or change branches.

### 6. Create and populate the backend environment

Check existing backend\.venv312 first. Keep it if it runs the correct interpreter and has valid dependencies. Otherwise create the expected environment using the verified x64 Python 3.12 executable:

    py -3.12 -c "import sys, platform, struct; print(sys.version); print(platform.machine()); print(struct.calcsize('P') * 8)"
    py -3.12 -m venv .\backend\.venv312

On ARM64 or machines with several Python installations, the py launcher might select a different architecture. Resolve and verify the intended x64 interpreter, then invoke its actual executable path; do not guess a username-specific Python path.

If an existing virtual environment is broken or has the wrong interpreter, explain the mismatch and preserve it before replacing it. Do not remove an arbitrary directory.

Install the checked-in pinned backend dependencies:

    & .\backend\.venv312\Scripts\python.exe -m pip install -r .\backend\requirements.lock.txt
    & .\backend\.venv312\Scripts\python.exe -m pip check

Use the virtual environment's Python directly; activation is not required. Do not change PowerShell policy to activate a virtual environment.

If locked dependencies cannot install, investigate interpreter architecture, version, wheel availability, proxy/certificate configuration and network errors. Do not silently rewrite the lock file or upgrade unrelated libraries. Report any unresolved package/version limitation accurately.

### 7. Initialize matching local environment files

The required local files are:

- .env: PostgreSQL user, generated password, database and published port.
- backend\.env: matching DATABASE_URL and CORS_ORIGINS.
- frontend\.env: VITE_API_BASE_URL=http://127.0.0.1:8000.

On a clean checkout where **none** of these three files exists:

    & .\backend\.venv312\Scripts\python.exe .\scripts\init_env.py

That script generates one random URL-safe password consistently for Compose and FastAPI and prints no secrets.

It deliberately refuses to run if **any** of the three files already exists. If configuration is partial, inspect missing key names and matching connection settings without displaying values. Preserve valid existing configuration; create only missing files using the existing matching credentials. Do not delete existing files to force the initializer to run.

Never copy the placeholder database password from .env.example as a working password. Do not copy ONDC example identities or a placeholder signing key into live configuration simply to run the admin app.

If a PostgreSQL volume already exists, changing .env does not change its database password. Diagnose the credential mismatch without deleting the volume or displaying the password.

### 8. Install frontend dependencies

From the repository root:

    Push-Location .\frontend
    try {
        npm.cmd ci
        # Check LASTEXITCODE and stop/report if installation failed.
    } finally {
        Pop-Location
    }

Use npm.cmd in Windows PowerShell to avoid the npm.ps1 execution-policy problem. Preserve package-lock.json; do not use npm audit fix --force or switch to a different package manager.

### 9. Check ports and Docker readiness

Check ports without terminating any process:

    Get-NetTCPConnection -State Listen -LocalPort 5432,8000,5173 -ErrorAction SilentlyContinue |
        Select-Object LocalAddress, LocalPort, OwningProcess

If ports are occupied, identify the process and whether it is the existing app/database. Reuse a healthy matching instance. Do not kill an unrelated service.

If an alternative PostgreSQL port is necessary, update only the root POSTGRES_PORT and the backend DATABASE_URL port consistently, preserving credentials. The current start.bat expects backend 8000 and frontend 5173; do not randomly change those without accounting for launcher checks, Vite, frontend API URL and CORS.

The Compose project name is deliberately ondc-fashion-seller to preserve an existing volume across the earlier branding rename. Do not rename it casually. Two checkouts on one computer may share that Compose identity; identify an existing instance before starting another.

Verify:

    docker info
    docker compose version

If Docker is still booting, wait a bounded time and recheck. If Docker Desktop needs first-run interaction, elevation, WSL repairs or a restart, explain the specific manual step.

### 10. Start the app

From the repository root:

    .\start.bat --no-pause

Check its exit code. The existing launcher should:

1. Verify environment files, Python environment, Node/npm, Docker and frontend dependencies.
2. Start Docker Desktop if needed and wait for its engine.
3. Run docker compose up -d --wait --wait-timeout 90.
4. Apply Alembic migrations.
5. Launch FastAPI on 127.0.0.1:8000 and Vite on 127.0.0.1:5173 in their own terminals.
6. Check expected app identity and readiness.

Do not launch duplicate instances when the script already started them. Do not say the app is ready just because terminal windows opened.

If the launcher fails, inspect its specific error and fix the cause. A manual diagnostic sequence is:

    docker compose up -d --wait --wait-timeout 90
    Push-Location .\backend
    try {
        & .\.venv312\Scripts\python.exe -m alembic upgrade head
        & .\.venv312\Scripts\python.exe -m alembic current
        & .\.venv312\Scripts\python.exe -m alembic check
    } finally {
        Pop-Location
    }

Check each command's exit code. Only if the corresponding server was not started already, use separate terminals:

Backend, from backend:

    .\.venv312\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Frontend, from frontend:

    npm.cmd run dev

### 11. Verify the application and checkout

Run:

    docker compose ps
    Invoke-RestMethod http://127.0.0.1:8000/
    Invoke-RestMethod http://127.0.0.1:8000/health
    (Invoke-WebRequest http://127.0.0.1:5173/ -UseBasicParsing).StatusCode

Expected:

- Backend identity name: SR Fashions.
- Health: status=ok and database=ok.
- Admin page returns HTTP 200.
- API documentation is available at http://127.0.0.1:8000/docs.

From backend, run the tests in that directory (the development-key subprocess test needs this working directory):

    Push-Location .\backend
    try {
        & .\.venv312\Scripts\python.exe -m pytest -q -p no:cacheprovider --tb=short
        & .\.venv312\Scripts\python.exe -m alembic current
        & .\.venv312\Scripts\python.exe -m alembic check
    } finally {
        Pop-Location
    }

At this revision, the normal suite has 148 passing tests and one optional PostgreSQL test skipped. If the code changes, report the actual count rather than forcing that historical number.

For optional actual PostgreSQL migration/worker verification, from backend set ONDC_TEST_POSTGRES=1 for the test invocation. Preserve and restore any prior value afterward. That test creates and removes its own temporary database schema, not the merchant schema. The previously verified complete count was 149 passing tests.

Build the frontend:

    Push-Location .\frontend
    try {
        npm.cmd run build
    } finally {
        Pop-Location
    }

Optionally run the live CRUD smoke test against this local migrated backend:

    & .\backend\.venv312\Scripts\python.exe .\scripts\smoke.py

Explain that smoke.py creates and removes only its own temporary seller/store/product records.

If tests cannot create temporary directories, use a new task-owned directory under an ignored .pytest_cache folder with pytest --basetemp, or request the required execution permission. Do not change Windows security settings or delete unrelated temporary files.

### 12. Explain first-run data and normal operation

A fresh clone does NOT include the author's PostgreSQL volume, .env files, local backups, seller IDs or existing products. An empty dashboard is normal.

The user can create a seller, store and products in the admin UI. If sample SR Fashions catalog data is wanted, explain that this command modifies the local catalog before running it:

    & .\backend\.venv312\Scripts\python.exe .\scripts\seed_catalog.py

Do not seed data silently. The seed script preserves existing matching SKUs; IDs can differ between machines.

Ordinary admin startup does not require ONDC keys, Registry access or publication metadata. Real network discovery remains outside this setup. No ONDC onboarding should happen.

After initial setup, future starts are simply:

    .\start.bat

Stop FastAPI/Vite with Ctrl+C in their terminals. Stop the database without removing data:

    docker compose stop

### 13. Final report

Report:

- OS and CPU architecture.
- Installed/reused Git, Python, Node/npm, Docker/Compose and WSL versions.
- Which prerequisites were installed and which manual actions remain.
- Repository path and Python environment path.
- Environment files present, without secret values.
- Database/container health and migration revision.
- Backend, frontend and Swagger URLs.
- Test/build/smoke commands and actual PASS/FAIL/SKIPPED results.
- Whether optional sample data was added.
- How to start and stop next time.

Do not claim success until the actual health and frontend checks pass. If blocked, state the exact prerequisite or permission and the concrete user action needed; do not fabricate successful installation or testing.

---

## Reference material for the setup agent

Recheck these official pages on the target machine; requirements can change:

- [Docker Desktop Windows installation and requirements](https://docs.docker.com/desktop/setup/install/windows-install/).
- [Docker WSL2 backend](https://docs.docker.com/desktop/features/wsl/).
- [Install WSL](https://learn.microsoft.com/en-us/windows/wsl/install).
- [Microsoft WinGet](https://learn.microsoft.com/en-us/windows/package-manager/winget/).
- [Python Windows downloads](https://www.python.org/downloads/windows/).
- [Node.js downloads](https://nodejs.org/en/download).
- [Vite prerequisites](https://vite.dev/guide/).

This prompt was prepared by inspecting this repository's launcher, configuration, dependency files and environment initializer on October 20, 2026. It is a setup workflow, not a claim that installation has been tested on every Windows computer.
