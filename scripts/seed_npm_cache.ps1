# Seed the NON-ROOT sandbox npm cache volume for offline Node sandbox installs (#56).
# The sandbox install container runs --user 1000:1000 with --network none; every
# package must therefore live in the specproof-npm-cache-1000 volume with uid 1000
# ownership (node:22-alpine's `node` user is exactly uid/gid 1000).
# Layout inside the volume (= the container's /home/node/.npm):
#   _cacache/        npm content-addressable cache (filled by the warm step)
#   _logs/           npm run logs (harmless)
# Steps 3-4 need network access (the sandbox itself never does). Re-run after
# dependency changes (package-lock.json) — re-warming is idempotent.
# Usage:
#   pwsh scripts/seed_npm_cache.ps1                        # create + chown volume only
#   pwsh scripts/seed_npm_cache.ps1 -RepoPath C:\path\to\repo   # + warm cache for that repo
param(
    [string]$RepoPath = ""
)
$ErrorActionPreference = "Stop"
$image  = "node:22-alpine"
$volume = "specproof-npm-cache-1000"

Write-Output "== 1/4 ensure npm cache volume exists =="
docker volume create $volume | Out-Null
if ($LASTEXITCODE -ne 0) { throw "volume create failed (exit $LASTEXITCODE)" }

Write-Output "== 2/4 chown volume to uid 1000 (the sandbox user) =="
# A fresh named volume mounts root-owned; uid 1000 could not write the cache.
docker run --rm -v "${volume}:/npm" $image sh -c "chown -R 1000:1000 /npm"
if ($LASTEXITCODE -ne 0) { throw "chown failed (exit $LASTEXITCODE)" }

if ($RepoPath -eq "") {
    Write-Output "== no -RepoPath given: volume is ready; warm it per repo later =="
    Write-Output "   pwsh scripts/seed_npm_cache.ps1 -RepoPath <repo-with-package-lock>"
    exit 0
}

$repo = Resolve-Path $RepoPath
if (-not (Test-Path (Join-Path $repo "package-lock.json"))) {
    throw "no package-lock.json under $repo — the offline install is lockfile-driven"
}

Write-Output "== 3/4 warm cache for $repo (ONLINE: downloads into the volume) =="
# node_modules is a container-internal tmpfs: the HOST workspace is never
# written (the repo bind is read-only), only the cache volume persists.
# --ignore-scripts matches the sandbox's install posture (no lifecycle scripts).
# The repo binds read-only at /repo and /work is a writable tmpfs: a tmpfs
# mountpoint cannot be created INSIDE a read-only bind (runc fails with a
# read-only file system error), so the repo is copied into /work instead.
# Only the cache volume persists — the copy is discarded with --rm.
# cp -r (not -a): nothing on a Windows bind mount preserves ownership and
# -a would spam 'can't preserve ownership' warnings as uid 1000.
docker run --rm --user 1000:1000 `
    -v "${volume}:/home/node/.npm" `
    -v "${repo}:/repo:ro" `
    --tmpfs /work:rw,uid=1000,gid=1000 `
    -e npm_config_cache=/home/node/.npm `
    -e npm_config_update_notifier=false `
    $image sh -c "cp -r /repo/. /work/ && cd /work && npm ci --ignore-scripts --no-audit --no-fund"
if ($LASTEXITCODE -ne 0) { throw "cache warm failed (exit $LASTEXITCODE)" }

Write-Output "== 4/4 offline smoke test (NO network: proves the cache is sufficient) =="
docker run --rm --user 1000:1000 --network none `
    -v "${volume}:/home/node/.npm" `
    -v "${repo}:/repo:ro" `
    --tmpfs /work:rw,uid=1000,gid=1000 `
    -e npm_config_cache=/home/node/.npm `
    -e npm_config_update_notifier=false `
    $image sh -c "cp -r /repo/. /work/ && cd /work && npm ci --offline --ignore-scripts --no-audit --no-fund"
if ($LASTEXITCODE -ne 0) { throw "offline smoke failed (exit $LASTEXITCODE) — cache is incomplete" }

Write-Output "== cache seeded and verified offline-ready for $repo =="
