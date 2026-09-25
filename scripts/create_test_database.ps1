#Requires -Version 5.1
<#
    create_test_database.ps1 - one-time bootstrap of an isolated MySQL schema
    for SpecProof's DB-backed tests (#75).

    Why this exists: `MySQLConfig` defaults `database` to the PRODUCT schema
    (specproof_phase0) and `password` to the product app credential, so an unset
    environment still reaches production. Measured 2026-09-26:
    verification_jobs held 177 rows and all 177 were repo_path '/test/repo'
    test residue - the product job table was 100% written by the unit suite,
    and the Dashboard counts those rows as real verification jobs.
    tests/conftest.py now refuses to run DB-backed tests against the product
    schema; this script creates the schema it wants instead.

    It only ever CREATES and GRANTS on the named test schema. It never touches
    specproof_phase0's data, and it refuses any target whose name could be
    mistaken for production, so it cannot be pointed at the live schema.

    The app user (specproof) has USAGE only outside specproof_phase0
    (measured), so this needs the root password your local compose declares:

        $env:MYSQL_ROOT_PASSWORD = <the value compose.phase0.yml uses>
        powershell scripts/create_test_database.ps1

    The password is read from the environment - never hard-coded here, never
    echoed, and passed to the container as MYSQL_PWD so it does not appear in
    that container's process arguments either.
#>
[CmdletBinding()]
param(
    [string]$Container = "specproof-mysql",
    [string]$TestDatabase = "specproof_test",
    [string]$AppUser = "specproof",
    [switch]$SkipMigrations
)

$ErrorActionPreference = "Stop"
$ProductDatabase = "specproof_phase0"
$Backtick = [char]96

function Stop-With([string]$message) {
    Write-Host "ABORT: $message" -ForegroundColor Red
    exit 2
}

# Fail closed before any privileged statement runs: the target must be a
# schema whose name cannot be mistaken for production. These three checks are
# also what makes the later string interpolation safe.
if ($TestDatabase -eq $ProductDatabase) {
    Stop-With "-TestDatabase must not be the product schema ($ProductDatabase)"
}
if ($TestDatabase -notmatch '^specproof_test[A-Za-z0-9_]*$') {
    Stop-With "-TestDatabase must match ^specproof_test[A-Za-z0-9_]*$ (got '$TestDatabase'); refusing to grant on an arbitrary schema"
}
if ($AppUser -notmatch '^[A-Za-z0-9_]+$') {
    Stop-With "-AppUser must be alphanumeric/underscore (got '$AppUser')"
}
if ($Container -notmatch '^[A-Za-z0-9._-]+$') {
    Stop-With "-Container must be a plain container name (got '$Container')"
}

$RootPassword = $env:MYSQL_ROOT_PASSWORD
if ([string]::IsNullOrEmpty($RootPassword)) {
    Stop-With "MYSQL_ROOT_PASSWORD is not set. Set it to the root password your local compose declares (see compose.phase0.yml), then re-run."
}

function Invoke-RootMysql([string]$sql) {
    # $sql is built only from regex-validated identifiers (see the guards
    # above); nothing here accepts caller-supplied SQL.
    $stmt = "SET NAMES utf8mb4; $sql"
    $out = docker exec -i -e MYSQL_PWD=$RootPassword $Container `
        mysql -u root --batch --skip-column-names -e $stmt 2>&1
    if ($LASTEXITCODE -ne 0) {
        Stop-With "mysql statement failed (exit $LASTEXITCODE): $stmt"
    }
    return ($out | Out-String).Trim()
}

function Quote-Id([string]$name) {
    return "$Backtick$name$Backtick"
}

Write-Host "1/4 creating schema $TestDatabase on container $Container"
$tdb = Quote-Id $TestDatabase
Invoke-RootMysql "CREATE DATABASE IF NOT EXISTS $tdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;" | Out-Null
Invoke-RootMysql "GRANT ALL PRIVILEGES ON $tdb.* TO '$AppUser'@'%'; FLUSH PRIVILEGES;" | Out-Null

if (-not $SkipMigrations) {
    Write-Host "2/4 applying pending migrations to $TestDatabase"
    $repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    $py = Join-Path $repo ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        Stop-With "interpreter not found at $py - create the repo venv first (see README)"
    }
    # storage.mysql is imported from the repo root, and the store reads its
    # config from the environment, so both must be set for this child only.
    Push-Location $repo
    try {
        $env:MYSQL_DATABASE = $TestDatabase
        & $py -c "from storage.mysql import MySQLStore; s = MySQLStore(); s.ensure_tables(); print('migrations applied to', s.config.database)"
    } finally {
        Pop-Location
    }
    if ($LASTEXITCODE -ne 0) {
        Stop-With "migration run failed for $TestDatabase (app user lacks DDL there?)"
    }
} else {
    Write-Host "2/4 migrations skipped"
}

Write-Host "3/4 verifying table parity with $ProductDatabase"
$testTables = [int](Invoke-RootMysql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$TestDatabase';")
$productTables = [int](Invoke-RootMysql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$ProductDatabase';")
$residue = [int](Invoke-RootMysql "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$ProductDatabase' AND table_name='verification_jobs';")
if ($residue -eq 1) {
    $productRows = [int](Invoke-RootMysql "SELECT COUNT(*) FROM $ProductDatabase.verification_jobs WHERE repo_path LIKE '/test/%';")
    Write-Host "  note: $ProductDatabase still holds $productRows '/test/%' job rows from earlier runs (this script deletes nothing)"
}

Write-Host "4/4 result"
Write-Host "  $TestDatabase    : $testTables tables"
Write-Host "  $ProductDatabase : $productTables tables (untouched by this script)"
if ($testTables -lt $productTables) {
    Write-Host "  WARNING: the test schema has FEWER tables than the product schema - DB-backed tests will hit missing tables, not silently skip." -ForegroundColor Yellow
}
Write-Host ""
Write-Host "Done. tests/conftest.py redirects DB-backed tests to $TestDatabase automatically;"
Write-Host "a shell can also name it directly:  `$env:MYSQL_DATABASE = '$TestDatabase'"
exit 0
