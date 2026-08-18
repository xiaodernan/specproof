# push_github.ps1 — push the current branch to the GitHub remote.
# Usage (token via process env, never stored in any file):
#   $env:GIT_TOKEN = "<your github_pat_...>"
#   pwsh scripts/push_github.ps1
# The token needs Contents: Read and write on the target repo
# (fine-grained PAT) or the repo scope (classic PAT).

$ErrorActionPreference = "Stop"

$token = $env:GIT_TOKEN
if (-not $token) {
    Write-Error "GIT_TOKEN environment variable is not set. Set it in the process env only."
    exit 1
}

$branch = git branch --show-current
if (-not $branch) {
    Write-Error "Not on a branch (detached HEAD?)"
    exit 1
}

git push "https://xiaodernan:$token@github.com/xiaodernan/specproof.git" "$branch"
Write-Output ("Pushed " + $branch + " to github.com/xiaodernan/specproof")
