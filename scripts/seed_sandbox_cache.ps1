# Seed the NON-ROOT sandbox Maven cache volume for offline sandbox runs (P6 / §12).
# The sandbox containers run --user 1000:1000 with --network none; every artifact
# must therefore live in the specproof-maven-cache-1000 volume with uid 1000
# ownership. The LEGACY volume specproof-maven-cache (root layout, mounted at
# /root/.m2 by long-running root-layout evaluations) is intentionally NEVER
# touched here — do not add steps that modify or prune it.
# Layout inside the volume (= the container's /home/maven/.m2):
#   repository/                 Maven dependency cache (copied from the host ~/.m2)
#   wrapper/dists/...           Maven Wrapper distribution (mvnw downloads it here)
# Steps 4-5 need network access (the sandbox itself never does). Re-run after
# dependency changes or when the demo wrapper distribution version changes.
$ErrorActionPreference = "Stop"
$repo   = Split-Path -Parent $PSScriptRoot
$demo   = Join-Path $repo "demo\spring-backend"
$hostM2 = Join-Path $env:USERPROFILE ".m2\repository"
$image  = "maven:3.9-eclipse-temurin-21"
$defaultVolume = "specproof-maven-cache-1000"
# Same knob sandbox/runner.py reads; naming a different volume here would
# seed one cache and build from another.
$volume = if ($env:SPECPROOF_SANDBOX_M2_VOLUME) { $env:SPECPROOF_SANDBOX_M2_VOLUME } else { $defaultVolume }

Write-Output "== 1/5 ensure cache + workspaces volumes exist (uid 1000) =="
docker volume create $volume | Out-Null
# Legacy root-era artifacts must not survive in the volume:
# settings-docker.xml redirects <localRepository> to an empty path if
# it is ever applied via -s, which would break offline builds.
docker run --rm -v "${volume}:/m2" $image sh -c "rm -f /m2/settings-docker.xml /m2/copy_reference_file.log"
docker volume create specproof-workspaces | Out-Null
# worker runs as uid 1000 and creates worktrees at the volume root
docker run --rm -v specproof-workspaces:/ws $image sh -c "chown 1000:1000 /ws"

Write-Output "== 2/5 copy host repository into volume =="
docker run --rm -v "${volume}:/home/maven/.m2" -v "${hostM2}:/host-m2:ro" $image sh -c "mkdir -p /home/maven/.m2/repository && cp -a /host-m2/. /home/maven/.m2/repository/"
if ($LASTEXITCODE -ne 0) { throw "seed copy failed (exit $LASTEXITCODE)" }
docker run --rm -v "${volume}:/m2" $image sh -c "chown -R 1000:1000 /m2"
if ($LASTEXITCODE -ne 0) { throw "chown failed (exit $LASTEXITCODE)" }

Write-Output "== 3/5 prepare disposable verification workspace (clean base-tag worktree) =="
# Verify against the committed base tag, not the working tree: in-flight
# changes or untracked leftovers (e.g. a pre-built target/) must not leak
# into the smoke test, and a pre-existing target/ would be root-owned
# in-container so the non-root Maven could not overwrite it.
$tmp = Join-Path $env:TEMP "specproof-seed-verify"
if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
Set-Location $repo
git worktree add --detach $tmp base | Out-Null
$tmpDemo = Join-Path $tmp "demo\spring-backend"
# git checks the wrapper script out with CRLF on Windows; the POSIX
# container cannot exec a CRLF shebang.
$mvnw = Join-Path $tmpDemo "mvnw"
$raw  = Get-Content $mvnw -Raw
(($raw -replace "`r`n", "`n") -replace "`r", "`n") | Set-Content -NoNewline -Encoding ascii $mvnw
# The wrapper jar is git-ignored (*.jar) and absent from clean checkouts;
# fetch it (wrapperUrl from .mvn/wrapper/maven-wrapper.properties) so
# step 4 can pull the wrapper distribution into the cache volume.
$jarDst = Join-Path $tmpDemo ".mvn\wrapper\maven-wrapper.jar"
$props = Get-Content (Join-Path $tmpDemo ".mvn\wrapper\maven-wrapper.properties") -Raw
$wrapperUrl = [regex]::Match($props, 'wrapperUrl=(.+)').Groups[1].Value.Trim()
curl.exe -fsSL -o $jarDst $wrapperUrl
if ($LASTEXITCODE -ne 0) { throw "wrapper jar download failed (exit $LASTEXITCODE)" }

Write-Output "== 4/5 fetch Maven Wrapper distribution (network required) =="
docker run --rm --user 1000:1000 -e MAVEN_USER_HOME=/home/maven/.m2 -e MAVEN_OPTS="-Duser.home=/home/maven" -v "${volume}:/home/maven/.m2" -v "${tmpDemo}:/work:ro" -w /work $image ./mvnw -q -v
if ($LASTEXITCODE -ne 0) { throw "wrapper dist fetch failed (exit $LASTEXITCODE)" }

Write-Output "== 5/5 verify the offline TEST phase (the phase the differential runs) =="
# test-compile is not enough (#530): it stops before surefire, so the
# JUnit-platform provider is never resolved and a cache missing it still
# passes. Run one real warmup test offline and require the surefire summary —
# a selector matching nothing would exit 0 without executing anything.
$warmupDst = Join-Path $tmpDemo "src\test\java\com\specproof\demo"
New-Item -ItemType Directory -Force -Path $warmupDst | Out-Null
Copy-Item (Join-Path $repo "scripts\seed_maven_cache_warmup\SpecProofSeedWarmupTest.java") $warmupDst
$offlineLog = docker run --rm --network none --user 1000:1000 -e MAVEN_USER_HOME=/home/maven/.m2 -e MAVEN_OPTS="-Duser.home=/home/maven" -v "${volume}:/home/maven/.m2" -v "${tmpDemo}:/work:ro" -v "${tmpDemo}/target:/work/target" -w /work $image mvn -B -o -Dtest=SpecProofSeedWarmupTest -DfailIfNoTests=false test 2>&1
if ($LASTEXITCODE -ne 0) { $offlineLog | Select-Object -Last 40; throw "offline test phase failed (exit $LASTEXITCODE)" }
if (-not ($offlineLog -match "Tests run: 1,")) { $offlineLog | Select-Object -Last 40; throw "offline test phase executed no test (vacuous cache check)" }

git worktree remove --force $tmp
Write-Output "SEED_OK: cache volume ready for sandboxed offline builds"
