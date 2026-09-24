# TrueBind local development: one command starts everything that is needed.
#   API + job worker (embedded) on http://127.0.0.1:8000   (docs: /docs)
#   Frontend on http://localhost:3000
# Both backend processes read backend/.env, so they always share ONE database
# (default backend/data/truebind-mvp.db; the legacy data/truebind.db is never touched).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

if (-not (Test-Path (Join-Path $backend ".env"))) {
    Copy-Item (Join-Path $backend ".env.example") (Join-Path $backend ".env")
    Write-Host "Created backend/.env from .env.example"
}
$py = if (Test-Path (Join-Path $backend ".venv\Scripts\python.exe")) { Join-Path $backend ".venv\Scripts\python.exe" } else { "python" }

Push-Location $backend
& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Database migration failed" }
Pop-Location

$api = Start-Process -PassThru -NoNewWindow -WorkingDirectory $backend -FilePath $py `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"
Write-Host "API + embedded worker starting (pid $($api.Id)). Waiting for readiness..."
for ($i = 0; $i -lt 60; $i++) {
    try { if ((Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health/ready).StatusCode -eq 200) { break } } catch {}
    Start-Sleep -Milliseconds 500
}
try {
    Push-Location $frontend
    if (-not (Test-Path "node_modules")) { npm install }
    npm run dev
} finally {
    Pop-Location
    Stop-Process -Id $api.Id -ErrorAction SilentlyContinue
}
