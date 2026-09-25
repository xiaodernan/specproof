# Seed the NON-ROOT sandbox pip wheelhouse volume for offline Python sandbox runs (#26).
# The sandbox install container runs --user 1000:1000 with --network none; every
# wheel must therefore live in the specproof-pip-wheelhouse-1000 volume, which the
# sandbox mounts READ-ONLY (untrusted test code cannot poison the dependency source).
# Layout inside the volume (= the container's /wheelhouse):
#   *.whl           pytest + its deps + the repo's requirements (pip download)
# Steps 3-4 need network access (the sandbox itself never does). Re-run after
# dependency changes (requirements.txt) - re-seeding is idempotent.
# Usage:
#   pwsh scripts/seed_pip_wheelhouse.ps1                        # create volume only
#   pwsh scripts/seed_pip_wheelhouse.ps1 -RepoPath C:\path\to\repo   # + seed pytest & requirements
param(
    [string]$RepoPath = ""
)
$ErrorActionPreference = "Stop"
$image   = "python:3.12-slim"
$volume  = "specproof-pip-wheelhouse-1000"

Write-Output "== 1/4 ensure wheelhouse volume exists =="
docker volume create $volume | Out-Null
if ($LASTEXITCODE -ne 0) { throw "volume create failed (exit $LASTEXITCODE)" }

Write-Output "== 2/4 chown volume to uid 1000 (the sandbox user) =="
docker run --rm -v "${volume}:/wheelhouse" $image sh -c "chown -R 1000:1000 /wheelhouse"
if ($LASTEXITCODE -ne 0) { throw "chown failed (exit $LASTEXITCODE)" }

if ($RepoPath -eq "") {
    Write-Output "== no -RepoPath given: volume is ready; seed it per repo later =="
    Write-Output "   pwsh scripts/seed_pip_wheelhouse.ps1 -RepoPath <repo-with-requirements>"
    exit 0
}

$repo = Resolve-Path $RepoPath
if (-not (Test-Path (Join-Path $repo "requirements.txt"))) {
    Write-Output "== note: no requirements.txt under $repo - seeding pytest only =="
}

Write-Output "== 3/4 download wheels for $repo (ONLINE) into the volume =="
# The repo binds read-only at /repo and /work is a writable tmpfs (a tmpfs
# mountpoint cannot be created INSIDE a read-only bind). pip download puts
# the wheels directly into the mounted volume.
# setuptools + wheel are ALWAYS seeded: a pyproject with a [project] table
# is installed editable with --no-build-isolation, which needs them in the
# venv (there is no network to fetch a build environment).
$args = "pip download --dest /wheelhouse pytest setuptools wheel"
if (Test-Path (Join-Path $repo "requirements.txt")) {
    $args = "$args -r /work/requirements.txt"
}
docker run --rm --user 1000:1000 `
    -v "${volume}:/wheelhouse" `
    -v "${repo}:/repo:ro" `
    --tmpfs /work:rw,exec,uid=1000,gid=1000 `
    -e PIP_CACHE_DIR=/tmp/pip-cache `
    $image sh -c "cp -r /repo/. /work/ && cd /work && $args"
if ($LASTEXITCODE -ne 0) { throw "wheel download failed (exit $LASTEXITCODE)" }

Write-Output "== 4/4 offline smoke test (NO network: proves the wheelhouse is sufficient) =="
# exec is REQUIRED on this tmpfs: the venv's interpreters live under /work
# and docker's tmpfs default is noexec (verified live: Permission denied).
docker run --rm --user 1000:1000 --network none `
    -v "${volume}:/wheelhouse:ro" `
    --tmpfs /work:rw,exec,uid=1000,gid=1000 `
    $image sh -c "python -m venv /work/.venv && /work/.venv/bin/pip install --no-index --find-links /wheelhouse pytest && /work/.venv/bin/python -m pytest --version"
if ($LASTEXITCODE -ne 0) { throw "offline smoke failed (exit $LASTEXITCODE) - wheelhouse is incomplete" }

Write-Output "== wheelhouse seeded and verified offline-ready for $repo =="
