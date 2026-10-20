$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$root = Split-Path -Parent $scriptDir

function Write-Header($msg) {
    Write-Host "`n============================================" -ForegroundColor Cyan
    Write-Host "  $msg" -ForegroundColor Cyan
    Write-Host "============================================`n" -ForegroundColor Cyan
}

function Run-Cmd($exe, $args, $desc) {
    Write-Host "[$desc] $exe $args" -ForegroundColor Gray
    $exitCode = 0
    try {
        & $exe $args
        $exitCode = $LASTEXITCODE
    } catch {
        $exitCode = 1
        Write-Host "  Execution error: $_" -ForegroundColor Red
    }
    if ($exitCode -ne 0) {
        Write-Host "  FAILED (exit $exitCode)" -ForegroundColor Red
        return $false
    } else {
        Write-Host "  PASSED" -ForegroundColor Green
        return $true
    }
}

$allPassed = $true
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Header "1. Ruff code style check"
$allPassed = (Run-Cmd $python "-m ruff check ." "ruff check") -and $allPassed

Write-Header "2. MyPy type check"
$allPassed = (Run-Cmd $python "-m mypy . --exclude tests --exclude artifacts --exclude demo --exclude scripts --exclude bench" "mypy") -and $allPassed

Write-Header "Gate Result Summary"
if ($allPassed) {
    Write-Host "ALL CHECKS PASSED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "SOME CHECKS FAILED" -ForegroundColor Red
    exit 1
}