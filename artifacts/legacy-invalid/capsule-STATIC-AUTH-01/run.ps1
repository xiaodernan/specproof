# ============================================================
# SpecProof Bug Capsule Replay — STATIC-AUTH-01
# Severity: MAJOR
# Contract: AUTH-01
# ============================================================

param(
    [string]$RepoDir = $env:SPECPROOF_REPO
)

if (-not $RepoDir) {
    Write-Host "Usage: .\run.ps1 <path-to-git-repo>"
    Write-Host "  or set `$env:SPECPROOF_REPO"
    Write-Host ""
    Write-Host "This script replays the differential test that detected"
    Write-Host "the regression reported in finding STATIC-AUTH-01."
    Write-Host "  Severity: MAJOR"
    Write-Host "  Contract: AUTH-01"
    Write-Host "  Evidence: static_regex_analysis"
    exit 1
}

if (-not (Test-Path "$RepoDir\.git")) {
    Write-Host "ERROR: $RepoDir is not a git repository"
    exit 1
}

$CapsuleDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseRef = if (Test-Path "$CapsuleDir\fixtures\base-ref.txt") {
    Get-Content "$CapsuleDir\fixtures\base-ref.txt"
} else { "base" }
$HeadRef = if (Test-Path "$CapsuleDir\fixtures\head-ref.txt") {
    Get-Content "$CapsuleDir\fixtures\head-ref.txt"
} else { "head-v1" }

Write-Host "============================================================"
Write-Host " SpecProof Bug Capsule Replay"
Write-Host "============================================================"
Write-Host " Finding:    STATIC-AUTH-01"
Write-Host " Severity:   MAJOR"
Write-Host " Contract:   AUTH-01"
Write-Host " Evidence:   static_regex_analysis"
Write-Host " Repo:       $RepoDir"
Write-Host " Base ref:   $BaseRef"
Write-Host " Head ref:   $HeadRef"
Write-Host "------------------------------------------------------------"
Write-Host " Description: @PreAuthorize removed from controller method — requires differential execution to confirm regression"
Write-Host "============================================================"
Write-Host ""

# ---- Prerequisites ----
Write-Host "[1/5] Checking prerequisites..."
try {
    $javaVer = java -version 2>&1 | Select-Object -First 1
    Write-Host "  Java:  $javaVer"
} catch {
    Write-Host "ERROR: Java not found. Install JDK 21+."
    exit 1
}

# ---- Apply generated test ----
Write-Host "[2/5] Applying generated test to repo..."
$TestSrc = "$CapsuleDir\generated-tests"
if ((Test-Path $TestSrc) -and (Get-ChildItem $TestSrc -ErrorAction SilentlyContinue)) {
    Write-Host "  Found generated test files:"
    Get-ChildItem $TestSrc | ForEach-Object { Write-Host "    $($_.Name)" }
    $destDir = "$RepoDir\src\test"
    if (Test-Path $destDir) {
        Copy-Item -Recurse -Force "$TestSrc\*" "$destDir\"
        Write-Host "  Tests copied to $destDir"
    }
} else {
    Write-Host "  No generated test files in capsule — using existing tests"
}

# ---- Run Base ----
Write-Host "[3/5] Running test on BASE ($BaseRef)..."
Push-Location $RepoDir
git checkout $BaseRef --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Cannot checkout base ref '$BaseRef'"
    Pop-Location
    exit 1
}

$mvnCmd = if (Test-Path ".\mvnw.cmd") {
    ".\mvnw.cmd"
} elseif (Test-Path ".\mvnw") {
    ".\mvnw"
} else {
    "mvn"
}
try {
    & $mvnCmd test -q 2>&1
    $BaseExit = $LASTEXITCODE
} catch {
    $BaseExit = 1
}
Write-Host "  Base test exit code: $BaseExit"

# ---- Run Head ----
Write-Host "[4/5] Running test on HEAD ($HeadRef)..."
git checkout $HeadRef --quiet 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Cannot checkout head ref '$HeadRef'"
    Pop-Location
    exit 1
}

try {
    & $mvnCmd test -q 2>&1
    $HeadExit = $LASTEXITCODE
} catch {
    $HeadExit = 1
}
Write-Host "  Head test exit code: $HeadExit"
Pop-Location

# ---- Verdict ----
Write-Host ""
Write-Host "============================================================"
Write-Host "[5/5] VERDICT"
Write-Host "============================================================"
Write-Host "  Base ($BaseRef):  exit=$BaseExit"
Write-Host "  Head ($HeadRef):  exit=$HeadExit"

if ($BaseExit -eq 0 -and $HeadExit -ne 0) {
    Write-Host ""
    Write-Host "  >> REGRESSION CONFIRMED <<"
    Write-Host "  Test passes in Base but fails in Head."
    Write-Host "  The PR introduced a breaking change."
    Write-Host ""
    Write-Host "  Finding: @PreAuthorize removed from controller method — requires differential execution to confirm regression"
} elseif ($BaseExit -ne 0 -and $HeadExit -eq 0) {
    Write-Host "  >> UNEXPECTED FIX <<"
    Write-Host "  Test fails in Base but passes in Head."
} elseif ($BaseExit -ne 0 -and $HeadExit -ne 0) {
    Write-Host "  >> AMBIGUOUS <<"
    Write-Host "  Test fails in both Base and Head."
} else {
    Write-Host "  >> COMPLIANT <<"
    Write-Host "  Test passes in both Base and Head."
    Write-Host "  Note: runtime test may not catch all regression types."
}
Write-Host "============================================================"
