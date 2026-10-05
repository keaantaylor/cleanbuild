# Runs TrueBind locally: the API on http://localhost:8000 (its own window) and
# the web app on http://localhost:3000 (this window). Ctrl+C stops the web app;
# close the API window to stop the API.
#   .\dev.ps1            start both
#   .\dev.ps1 -WebOnly   start only the web app (API already running)
param([switch]$WebOnly)

$root = $PSScriptRoot
$backend = Join-Path $root "truebind-web\backend"
$frontend = Join-Path $root "truebind-web\frontend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not $WebOnly) {
    if (-not (Test-Path $python)) {
        Write-Host "No backend virtualenv at $python. Create it first: py -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt" -ForegroundColor Yellow
        exit 1
    }
    $api = "Set-Location '$backend'; & '$python' -m alembic upgrade head; & '$python' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $api | Out-Null
    Write-Host "API starting on http://localhost:8000 (separate window)"
}

Set-Location $frontend
if (-not (Test-Path (Join-Path $frontend "node_modules"))) { npm install }
Write-Host "Web app on http://localhost:3000  ·  design system: http://localhost:3000/design-system"
npm run dev
