# SpecProof web UI build script (Task B).
# Requires Node.js >= 18 and npm. Output: apps/web/dist (served by api/server.py).
# Usage: .\scripts\build_web.ps1

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$webDir = Join-Path $repoRoot "apps\web"

Write-Host "== SpecProof web build ==" -ForegroundColor Cyan
Write-Host "web dir : $webDir"
Write-Host "node    : $(node --version)"
Write-Host "npm     : $(npm --version)"

Push-Location $webDir
try {
    Write-Host "[1/3] npm install (ci-style; fallback to install)" -ForegroundColor Yellow
    npm install --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

    Write-Host "[2/3] npm run build (tsc + vite)" -ForegroundColor Yellow
    npm run build
    if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
} finally {
    Pop-Location
}

$dist = Join-Path $webDir "dist"
if (-not (Test-Path (Join-Path $dist "index.html"))) {
    throw "build succeeded but apps/web/dist/index.html is missing"
}

Write-Host "[3/3] OK - SPA ready at $dist" -ForegroundColor Green
Write-Host "FastAPI (api/server.py) will serve it at / on the next start." -ForegroundColor Green
