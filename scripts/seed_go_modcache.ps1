# Seed the NON-ROOT sandbox Go module cache volume for offline Go sandbox runs
# (Phase 2.6). The sandbox container runs --user 1000:1000 with --network none;
# every module must therefore live in the specproof-go-modcache-1000 volume,
# which the sandbox mounts rw (go writes lock files and extracts modules there
# — same trust model as the Maven/npm caches).
# Steps 3-4 need network access (the sandbox itself never does). Re-run after
# dependency changes (go.mod) — re-seeding is idempotent.
# Usage:
#   pwsh scripts/seed_go_modcache.ps1                        # create volume only
#   pwsh scripts/seed_go_modcache.ps1 -RepoPath C:\path\to\repo   # + warm & verify
param(
    [string]$RepoPath = ""
)
$ErrorActionPreference = "Stop"
$image  = "golang:1.23-alpine"
$volume = "specproof-go-modcache-1000"

Write-Output "== 1/4 ensure module cache volume exists =="
docker volume create $volume | Out-Null
if ($LASTEXITCODE -ne 0) { throw "volume create failed (exit $LASTEXITCODE)" }

Write-Output "== 2/4 chown volume to uid 1000 (the sandbox user) =="
docker run --rm -v "${volume}:/go/pkg/mod" $image sh -c "chown -R 1000:1000 /go/pkg/mod"
if ($LASTEXITCODE -ne 0) { throw "chown failed (exit $LASTEXITCODE)" }

if ($RepoPath -eq "") {
    Write-Output "== no -RepoPath given: volume is ready; warm it per repo later =="
    Write-Output "   pwsh scripts/seed_go_modcache.ps1 -RepoPath <repo-with-go.mod>"
    exit 0
}

$repo = Resolve-Path $RepoPath
if (-not (Test-Path (Join-Path $repo "go.mod"))) {
    throw "no go.mod under $repo — the offline install is module-driven"
}

# GONOSUMDB=* skips the checksum DATABASE (its state dir lives outside the
# volume and uid 1000 cannot write it) — but go.sum in the repo still pins
# every hash, so supply-chain verification is NOT lost; the sumdb only
# covers modules go.sum has never seen.
Write-Output "== 3/4 warm module cache for $repo (ONLINE) =="
# The repo binds read-only at /repo; /work is an EXEC-capable tmpfs (a tmpfs
# mountpoint cannot be created INSIDE a read-only bind, and go test needs to
# execute compiled binaries from its temp dir — docker tmpfs defaults to
# noexec, verified live in #26). Only the cache volume persists.
docker run --rm --user 1000:1000 `
    -v "${volume}:/go/pkg/mod" `
    -v "${repo}:/repo:ro" `
    --tmpfs /work:rw,exec,uid=1000,gid=1000 `
    -e GOPROXY="https://proxy.golang.org,direct" `
    -e GONOSUMDB="*" `
    -e GOCACHE=/tmp/go-build `
    $image sh -c "cp -r /repo/. /work/ && cd /work && go mod download all"
if ($LASTEXITCODE -ne 0) { throw "module warm failed (exit $LASTEXITCODE)" }

Write-Output "== 4/4 offline smoke test (NO network: proves the cache is sufficient) =="
docker run --rm --user 1000:1000 --network none `
    -v "${volume}:/go/pkg/mod" `
    -v "${repo}:/repo:ro" `
    --tmpfs /work:rw,exec,uid=1000,gid=1000 `
    -e GOPROXY=off `
    -e GOFLAGS=-mod=mod `
    -e GOCACHE=/tmp/go-build `
    $image sh -c "cp -r /repo/. /work/ && cd /work && go build ./... && go mod download all"
if ($LASTEXITCODE -ne 0) { throw "offline smoke failed (exit $LASTEXITCODE) - cache is incomplete" }

Write-Output "== module cache seeded and verified offline-ready for $repo =="
