# Seed the GRADLE_USER_HOME volume used by the offline Gradle sandbox (#232 / #492).
# The sandbox containers run --user 1000:1000 with --network none, so every
# dependency must already live in specproof-gradle-home-1000 with uid 1000
# ownership. This script is the step the GradleAdapter's OFFLINE_POLICY names.
#
# Usage:
#   powershell -File scripts/seed_gradle_home.ps1 -ProjectPath C:\path\to\gradle-project
#
# There is no Gradle demo repository in this repo (demo/spring-backend is Maven),
# so the project to seed MUST be passed in: Gradle dependency sets are
# project-specific, unlike the Maven cache which the demo alone can populate.
#
# What it does, in order:
#   1. create the volume and hand it to uid 1000 (Gradle cannot unpack
#      libnative-platform.so into a root-owned home -> "Could not initialize
#      native services" before any task runs);
#   2. copy the project to a temp workspace (never seed from the live tree:
#      a pre-existing root-owned build/ or .gradle/ would poison the run);
#   3. ONLINE build against the volume, using the IMAGE'S OWN `gradle` binary —
#      the same binary the sandbox invokes. A project wrapper would download a
#      different distribution into the volume and the sandbox would never use it;
#   4. OFFLINE verification with --network none, workspace :ro and only .gradle
#      + build writable — exactly the GRADLE_PROFILE mount shape. A cache miss
#      must fail HERE, not inside a real verification run.
param(
    [Parameter(Mandatory = $true)][string]$ProjectPath,
    [string]$Image  = "gradle:8.10-jdk21",
    [string]$Volume = "specproof-gradle-home-1000",
    [string]$Task   = "test"
)

$ErrorActionPreference = "Stop"
$gradleUserHome = "/gradle-home"
$gradleOpts = "-Dorg.gradle.daemon=false -Dorg.gradle.java.installations.auto-download=false"

if (-not (Test-Path (Join-Path $ProjectPath "build.gradle")) -and
    -not (Test-Path (Join-Path $ProjectPath "build.gradle.kts"))) {
    throw "not a Gradle project (no build.gradle / build.gradle.kts): $ProjectPath"
}
$ProjectPath = (Resolve-Path $ProjectPath).Path

Write-Output "== 1/5 create volume and give it to uid 1000 =="
docker volume create $Volume | Out-Null
docker run --rm -v "${Volume}:${gradleUserHome}" alpine sh -c "chown 1000:1000 ${gradleUserHome}"
if ($LASTEXITCODE -ne 0) { throw "volume chown failed (exit $LASTEXITCODE)" }

Write-Output "== 2/5 copy project into a disposable workspace =="
$tmp = Join-Path $env:TEMP "specproof-seed-gradle"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
New-Item -ItemType Directory -Path $tmp | Out-Null
Copy-Item -Path (Join-Path $ProjectPath "*") -Destination $tmp -Recurse -Force
# Build outputs and project-local caches from the source tree must not be reused:
# they may be root-owned in-container, and a stale build/ would hide a cache miss.
foreach ($junk in @("build", ".gradle", ".git")) {
    $p = Join-Path $tmp $junk
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
}
New-Item -ItemType Directory -Path (Join-Path $tmp ".gradle") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $tmp "build") -Force | Out-Null

Write-Output "== 3/5 resolve dependencies ONLINE into the volume =="
docker run --rm --user 1000:1000 `
    -e "GRADLE_USER_HOME=$gradleUserHome" -e "GRADLE_OPTS=$gradleOpts" `
    -v "${Volume}:${gradleUserHome}" -v "${tmp}:/work" -w /work `
    $Image gradle --no-daemon --console=plain $Task
if ($LASTEXITCODE -ne 0) { throw "online seed build failed (exit $LASTEXITCODE)" }

Write-Output "== 4/5 verify OFFLINE with the sandbox mount shape =="
# Wipe the online phase's outputs FIRST. Otherwise every task reports UP-TO-DATE
# and this step proves nothing about offline resolution — it would pass on an
# empty volume. The verification is only meaningful from a cold workspace.
foreach ($out in @("build", ".gradle")) {
    $p = Join-Path $tmp $out
    if (Test-Path $p) { Remove-Item -Recurse -Force $p }
    New-Item -ItemType Directory -Path $p -Force | Out-Null
}
docker run --rm --network none --user 1000:1000 `
    -e "GRADLE_USER_HOME=$gradleUserHome" -e "GRADLE_OPTS=$gradleOpts" `
    -v "${Volume}:${gradleUserHome}" `
    -v "${tmp}:/work:ro" `
    -v "${tmp}/.gradle:/work/.gradle" `
    -v "${tmp}/build:/work/build" `
    -w /work `
    $Image gradle --no-daemon --offline --console=plain $Task
if ($LASTEXITCODE -ne 0) { throw "offline verification failed (exit $LASTEXITCODE)" }

Write-Output "== 5/5 hand the volume's new files to uid 1000 =="
docker run --rm -v "${Volume}:${gradleUserHome}" alpine sh -c "chown -R 1000:1000 ${gradleUserHome}"
if ($LASTEXITCODE -ne 0) { throw "final chown failed (exit $LASTEXITCODE)" }

Remove-Item -Recurse -Force $tmp
Write-Output "SEED_OK: ${Volume} ready for sandboxed offline Gradle builds"
