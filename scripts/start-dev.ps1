$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot 'backend\.venv312\Scripts\python.exe'
$launcher = Join-Path $projectRoot 'start.bat'
$env:PATH = "$env:ProgramFiles\nodejs;$env:ProgramFiles\Docker\Docker\resources\bin;$env:PATH"

function Test-Port([int]$Port) {
    $tcp = New-Object System.Net.Sockets.TcpClient
    try { return $tcp.ConnectAsync('127.0.0.1', $Port).Wait(500) -and $tcp.Connected }
    catch { return $false }
    finally { $tcp.Dispose() }
}
function Test-App([string]$Kind) {
    try {
        if ($Kind -eq 'backend') {
            $info = Invoke-RestMethod 'http://127.0.0.1:8000/' -TimeoutSec 3
            $health = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 3
            return $info.name -eq 'SR Fashions' -and $health.status -eq 'ok'
        }
        $page = Invoke-WebRequest 'http://127.0.0.1:5173/' -UseBasicParsing -TimeoutSec 3
        return $page.StatusCode -eq 200 -and $page.Content.Contains('SR Fashions | Retailer Admin')
    } catch { return $false }
}
function Wait-App([string]$Kind) {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (Test-App $Kind) { return }
        Start-Sleep -Seconds 1
    }
    throw "$Kind did not become ready. Check its terminal window for errors."
}

try {
    Set-Location -LiteralPath $projectRoot
    Write-Host 'Starting SR Fashions...' -ForegroundColor Cyan
    foreach ($relative in @('.env', 'backend\.env', 'frontend\.env')) {
        if (!(Test-Path -LiteralPath (Join-Path $projectRoot $relative))) {
            throw "Missing $relative. Follow SETUP.md to configure the environment."
        }
    }
    if (!(Test-Path -LiteralPath $python)) { throw 'Python virtual environment missing. Follow SETUP.md to install backend dependencies.' }
    foreach ($command in @('docker.exe', 'node.exe', 'npm.cmd')) {
        if (!(Get-Command $command -ErrorAction SilentlyContinue)) { throw "$command is missing. Install the prerequisites in SETUP.md." }
    }
    if (!(Test-Path -LiteralPath (Join-Path $projectRoot 'frontend\node_modules\vite\bin\vite.js'))) {
        throw 'Frontend dependencies missing. Run npm.cmd ci in frontend first.'
    }
    & $env:ComSpec /c 'docker.exe info >nul 2>&1'
    if ($LASTEXITCODE -ne 0) {
        $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
        if (!(Test-Path -LiteralPath $desktop)) { throw 'Docker engine is unavailable. Start Docker Desktop manually.' }
        Write-Host 'Starting Docker Desktop; waiting for its engine...'
        Start-Process -FilePath $desktop -WindowStyle Hidden
        $ready = $false
        for ($attempt = 0; $attempt -lt 60; $attempt++) {
            Start-Sleep -Seconds 2
            & $env:ComSpec /c 'docker.exe info >nul 2>&1'
            if ($LASTEXITCODE -eq 0) { $ready = $true; break }
        }
        if (!$ready) { throw 'Docker did not become ready. Check Docker Desktop and WSL, then retry.' }
    }
    Write-Host 'Starting PostgreSQL...'
    & docker.exe compose up -d --wait --wait-timeout 90
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed.' }
    Write-Host 'Applying database migrations...'
    Push-Location (Join-Path $projectRoot 'backend')
    try {
        & $python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw 'Database migration failed.' }
    } finally { Pop-Location }

    foreach ($service in @(@{Kind='backend';Port=8000}, @{Kind='frontend';Port=5173})) {
        if (Test-Port $service.Port) {
            if (!(Test-App $service.Kind)) { throw "Port $($service.Port) is occupied but the expected app is not healthy. Check the existing process before retrying." }
            Write-Host "Reusing healthy $($service.Kind) on port $($service.Port)."
        } else {
            # Visible terminals are intentional: the user can read logs and stop with Ctrl+C.
            $arguments = '/k ""{0}" --{1}"' -f $launcher, $service.Kind
            Start-Process -FilePath $env:ComSpec -ArgumentList $arguments -WorkingDirectory $projectRoot
            Wait-App $service.Kind
        }
    }
    Write-Host ''
    Write-Host 'SR Fashions is ready.' -ForegroundColor Green
    Write-Host 'Admin:    http://127.0.0.1:5173'
    Write-Host 'API docs: http://127.0.0.1:8000/docs'
    Write-Host 'Stop the app servers with Ctrl+C in their windows.'
    Write-Host 'Stop the database later with: docker compose stop'
    exit 0
} catch {
    Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
