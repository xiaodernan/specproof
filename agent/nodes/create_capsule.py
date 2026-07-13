"""create_capsule node — package Bug Capsules for BLOCKER/MAJOR findings."""

import json
import os
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from agent.state import Phase0State


def create_capsule_node(state: Phase0State) -> dict:
    """Create Bug Capsule zip files for each confirmed finding.

    Each capsule contains manifest, requirement, contract, finding,
    generated tests, fixtures, and a run.sh script.
    """
    confirmed_findings = state.get("confirmed_findings", [])
    contracts = state.get("contracts", [])
    requirement_text = state.get("requirement_text", "")
    generated_tests_path = state.get("generated_tests_path", "")
    capsules: list[str] = []

    output_dir = Path("capsules")
    output_dir.mkdir(parents=True, exist_ok=True)

    for finding in confirmed_findings:
        if finding.get("severity") not in ("BLOCKER", "MAJOR"):
            continue

        fid = finding.get("id", str(uuid.uuid4())[:8])
        capsule_dir = output_dir / f"capsule-{fid}"
        capsule_dir.mkdir(parents=True, exist_ok=True)

        # manifest.json
        manifest = {
            "finding_id": fid,
            "severity": finding.get("severity"),
            "confidence": finding.get("confidence"),
            "created_at": datetime.now(UTC).isoformat(),
            "contract_id": finding.get("contract_id"),
            "evidence_type": finding.get("evidence_type"),
        }
        (capsule_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # requirement.json
        (capsule_dir / "requirement.json").write_text(
            json.dumps({"text": requirement_text}, indent=2), encoding="utf-8"
        )

        # contract.json
        matching = [c for c in contracts if c.get("id") == finding.get("contract_id")]
        (capsule_dir / "contract.json").write_text(
            json.dumps(matching[0] if matching else {}, indent=2), encoding="utf-8"
        )

        # finding.json
        (capsule_dir / "finding.json").write_text(json.dumps(finding, indent=2), encoding="utf-8")

        # generated-tests/
        tests_dir = capsule_dir / "generated-tests"
        tests_dir.mkdir(exist_ok=True)
        if generated_tests_path and os.path.exists(generated_tests_path):
            dest = tests_dir / Path(generated_tests_path).name
            dest.write_text(Path(generated_tests_path).read_text(encoding="utf-8"))

        # fixtures/
        fixtures_dir = capsule_dir / "fixtures"
        fixtures_dir.mkdir(exist_ok=True)
        (fixtures_dir / "base-ref.txt").write_text(state.get("base_ref", ""))
        (fixtures_dir / "head-ref.txt").write_text(state.get("head_ref", ""))

        # environment/
        env_dir = capsule_dir / "environment"
        env_dir.mkdir(exist_ok=True)
        (env_dir / ".env.template").write_text(
            "LLM_API_KEY=replace_me\nMYSQL_PASSWORD=replace_me\nREDIS_PASSWORD=replace_me\n"
        )

        # run.sh — executable replay script (bash)
        run_script = _build_replay_script(
            fid=fid,
            finding=finding,
            capsule_dir_name=f"capsule-{fid}",
            is_windows=False,
        )
        run_path = capsule_dir / "run.sh"
        run_path.write_text(run_script, encoding="utf-8")

        # run.ps1 — executable replay script (PowerShell)
        ps1_script = _build_replay_script(
            fid=fid,
            finding=finding,
            capsule_dir_name=f"capsule-{fid}",
            is_windows=True,
        )
        ps1_path = capsule_dir / "run.ps1"
        ps1_path.write_text(ps1_script, encoding="utf-8")

        # README.md
        readme = (
            f"# Bug Capsule: {fid}\n\n"
            f"**Severity:** {finding.get('severity')}\n"
            f"**Confidence:** {finding.get('confidence')}\n\n"
            f"## Finding\n{finding.get('description', 'No description')}\n\n"
            f"## Replay\n```bash\ncd {capsule_dir} && bash run.sh\n```\n"
        )
        (capsule_dir / "README.md").write_text(readme, encoding="utf-8")

        # Package as zip
        zip_path = output_dir / f"capsule-{fid}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for file_path in capsule_dir.rglob("*"):
                arcname = file_path.relative_to(capsule_dir)
                zf.write(file_path, arcname)

        capsules.append(str(zip_path.resolve()))

    return {"capsules": capsules}


def _build_replay_script(
    fid: str,
    finding: dict,
    capsule_dir_name: str,
    is_windows: bool = False,
) -> str:
    """Build a real executable replay script (bash or PowerShell).

    The script checks out base/head refs from the target repo, applies the
    generated test, runs differential execution, and compares results.
    """
    severity = finding.get("severity", "UNKNOWN")
    contract_id = finding.get("contract_id", "")
    description = finding.get("description", finding.get("detail", "No description"))
    evidence_type = finding.get("evidence_type", "unknown")

    if is_windows:
        return _build_ps1_script(
            fid, severity, contract_id, description, evidence_type, capsule_dir_name
        )
    else:
        return _build_sh_script(
            fid, severity, contract_id, description, evidence_type, capsule_dir_name
        )


def _build_sh_script(
    fid: str,
    severity: str,
    contract_id: str,
    description: str,
    evidence_type: str,
    capsule_dir_name: str,
) -> str:
    """Build a bash replay script."""
    return f"""#!/bin/bash
set -euo pipefail

# ============================================================
# SpecProof Bug Capsule Replay — {fid}
# Severity: {severity}
# Contract: {contract_id}
# ============================================================

REPO_DIR="${{1:-$SPECPROOF_REPO}}"
if [ -z "$REPO_DIR" ]; then
    echo "Usage: bash run.sh <path-to-git-repo>"
    echo "  or set SPECPROOF_REPO environment variable"
    echo ""
    echo "This script replays the differential test that detected"
    echo "the regression reported in finding {fid}."
    echo "  Severity: {severity}"
    echo "  Contract: {contract_id}"
    echo "  Evidence: {evidence_type}"
    exit 1
fi

if [ ! -d "$REPO_DIR/.git" ]; then
    echo "ERROR: $REPO_DIR is not a git repository"
    exit 1
fi

CAPSULE_DIR="$(cd "$(dirname "$0")" && pwd)"
BASE_REF=$(cat "$CAPSULE_DIR/fixtures/base-ref.txt" 2>/dev/null || echo "base")
HEAD_REF=$(cat "$CAPSULE_DIR/fixtures/head-ref.txt" 2>/dev/null || echo "head-v1")

echo "============================================================"
echo " SpecProof Bug Capsule Replay"
echo "============================================================"
echo " Finding:    {fid}"
echo " Severity:   {severity}"
echo " Contract:   {contract_id}"
echo " Evidence:   {evidence_type}"
echo " Repo:       $REPO_DIR"
echo " Base ref:   $BASE_REF"
echo " Head ref:   $HEAD_REF"
echo "------------------------------------------------------------"
echo " Description: {description}"
echo "============================================================"
echo ""

# ---- Prerequisites ----
echo "[1/5] Checking prerequisites..."

if ! command -v java &>/dev/null; then
    echo "ERROR: Java not found. Install JDK 21+."
    exit 1
fi
JAVA_VER=$(java -version 2>&1 | head -1)
echo "  Java:  $JAVA_VER"

# ---- Apply generated test ----
echo "[2/5] Applying generated test to repo..."
TEST_SRC="$CAPSULE_DIR/generated-tests"
if [ -d "$TEST_SRC" ] && [ "$(ls -A "$TEST_SRC" 2>/dev/null)" ]; then
    echo "  Found generated test files:"
    ls -la "$TEST_SRC/"
    # Copy test files to the repo's test directory
    if [ -d "$REPO_DIR/src/test" ]; then
        cp -r "$TEST_SRC"/* "$REPO_DIR/src/test/" 2>/dev/null || true
        echo "  Tests copied to $REPO_DIR/src/test/"
    fi
else
    echo "  No generated test files in capsule — using existing tests"
fi

# ---- Run Base ----
echo "[3/5] Running test on BASE ($BASE_REF)..."
cd "$REPO_DIR"
git checkout "$BASE_REF" --quiet 2>/dev/null || {{
    echo "ERROR: Cannot checkout base ref '$BASE_REF'"
    exit 1
}}

BASE_EXIT=0
if [ -f "./mvnw" ] || [ -f "./mvnw.cmd" ]; then
    MVN_CMD="./mvnw"
    [ -f "./mvnw.cmd" ] && MVN_CMD="./mvnw.cmd"
    $MVN_CMD test -q 2>&1 || BASE_EXIT=$?
else
    mvn test -q 2>&1 || BASE_EXIT=$?
fi
echo "  Base test exit code: $BASE_EXIT"

# ---- Run Head ----
echo "[4/5] Running test on HEAD ($HEAD_REF)..."
git checkout "$HEAD_REF" --quiet 2>/dev/null || {{
    echo "ERROR: Cannot checkout head ref '$HEAD_REF'"
    exit 1
}}

HEAD_EXIT=0
if [ -f "./mvnw" ] || [ -f "./mvnw.cmd" ]; then
    MVN_CMD="./mvnw"
    [ -f "./mvnw.cmd" ] && MVN_CMD="./mvnw.cmd"
    $MVN_CMD test -q 2>&1 || HEAD_EXIT=$?
else
    mvn test -q 2>&1 || HEAD_EXIT=$?
fi
echo "  Head test exit code: $HEAD_EXIT"

# ---- Verdict ----
echo ""
echo "============================================================"
echo "[5/5] VERDICT"
echo "============================================================"
echo "  Base ($BASE_REF):  exit=$BASE_EXIT"
echo "  Head ($HEAD_REF):  exit=$HEAD_EXIT"

if [ "$BASE_EXIT" -eq 0 ] && [ "$HEAD_EXIT" -ne 0 ]; then
    echo ""
    echo "  >> REGRESSION CONFIRMED <<"
    echo "  Test passes in Base but fails in Head."
    echo "  The PR introduced a breaking change."
    echo ""
    echo "  Finding: {description}"
elif [ "$BASE_EXIT" -ne 0 ] && [ "$HEAD_EXIT" -eq 0 ]; then
    echo "  >> UNEXPECTED FIX <<"
    echo "  Test fails in Base but passes in Head."
elif [ "$BASE_EXIT" -ne 0 ] && [ "$HEAD_EXIT" -ne 0 ]; then
    echo "  >> AMBIGUOUS <<"
    echo "  Test fails in both Base and Head."
else
    echo "  >> COMPLIANT <<"
    echo "  Test passes in both Base and Head."
    echo "  Note: runtime test may not catch all regression types."
fi
echo "============================================================"

# Return to original state
git checkout "$HEAD_REF" --quiet 2>/dev/null || true
"""


def _build_ps1_script(
    fid: str,
    severity: str,
    contract_id: str,
    description: str,
    evidence_type: str,
    capsule_dir_name: str,
) -> str:
    """Build a PowerShell replay script for Windows."""
    return f"""# ============================================================
# SpecProof Bug Capsule Replay — {fid}
# Severity: {severity}
# Contract: {contract_id}
# ============================================================

param(
    [string]$RepoDir = $env:SPECPROOF_REPO
)

if (-not $RepoDir) {{
    Write-Host "Usage: .\\run.ps1 <path-to-git-repo>"
    Write-Host "  or set `$env:SPECPROOF_REPO"
    Write-Host ""
    Write-Host "This script replays the differential test that detected"
    Write-Host "the regression reported in finding {fid}."
    Write-Host "  Severity: {severity}"
    Write-Host "  Contract: {contract_id}"
    Write-Host "  Evidence: {evidence_type}"
    exit 1
}}

if (-not (Test-Path "$RepoDir\\.git")) {{
    Write-Host "ERROR: $RepoDir is not a git repository"
    exit 1
}}

$CapsuleDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseRef = if (Test-Path "$CapsuleDir\\fixtures\\base-ref.txt") {{
    Get-Content "$CapsuleDir\\fixtures\\base-ref.txt"
}} else {{ "base" }}
$HeadRef = if (Test-Path "$CapsuleDir\\fixtures\\head-ref.txt") {{
    Get-Content "$CapsuleDir\\fixtures\\head-ref.txt"
}} else {{ "head-v1" }}

Write-Host "============================================================"
Write-Host " SpecProof Bug Capsule Replay"
Write-Host "============================================================"
Write-Host " Finding:    {fid}"
Write-Host " Severity:   {severity}"
Write-Host " Contract:   {contract_id}"
Write-Host " Evidence:   {evidence_type}"
Write-Host " Repo:       $RepoDir"
Write-Host " Base ref:   $BaseRef"
Write-Host " Head ref:   $HeadRef"
Write-Host "------------------------------------------------------------"
Write-Host " Description: {description}"
Write-Host "============================================================"
Write-Host ""

# ---- Prerequisites ----
Write-Host "[1/5] Checking prerequisites..."
try {{
    $javaVer = java -version 2>&1 | Select-Object -First 1
    Write-Host "  Java:  $javaVer"
}} catch {{
    Write-Host "ERROR: Java not found. Install JDK 21+."
    exit 1
}}

# ---- Apply generated test ----
Write-Host "[2/5] Applying generated test to repo..."
$TestSrc = "$CapsuleDir\\generated-tests"
if ((Test-Path $TestSrc) -and (Get-ChildItem $TestSrc -ErrorAction SilentlyContinue)) {{
    Write-Host "  Found generated test files:"
    Get-ChildItem $TestSrc | ForEach-Object {{ Write-Host "    $($_.Name)" }}
    $destDir = "$RepoDir\\src\\test"
    if (Test-Path $destDir) {{
        Copy-Item -Recurse -Force "$TestSrc\\*" "$destDir\\"
        Write-Host "  Tests copied to $destDir"
    }}
}} else {{
    Write-Host "  No generated test files in capsule — using existing tests"
}}

# ---- Run Base ----
Write-Host "[3/5] Running test on BASE ($BaseRef)..."
Push-Location $RepoDir
git checkout $BaseRef --quiet 2>$null
if ($LASTEXITCODE -ne 0) {{
    Write-Host "ERROR: Cannot checkout base ref '$BaseRef'"
    Pop-Location
    exit 1
}}

$mvnCmd = if (Test-Path ".\\mvnw.cmd") {{
    ".\\mvnw.cmd"
}} elseif (Test-Path ".\\mvnw") {{
    ".\\mvnw"
}} else {{
    "mvn"
}}
try {{
    & $mvnCmd test -q 2>&1
    $BaseExit = $LASTEXITCODE
}} catch {{
    $BaseExit = 1
}}
Write-Host "  Base test exit code: $BaseExit"

# ---- Run Head ----
Write-Host "[4/5] Running test on HEAD ($HeadRef)..."
git checkout $HeadRef --quiet 2>$null
if ($LASTEXITCODE -ne 0) {{
    Write-Host "ERROR: Cannot checkout head ref '$HeadRef'"
    Pop-Location
    exit 1
}}

try {{
    & $mvnCmd test -q 2>&1
    $HeadExit = $LASTEXITCODE
}} catch {{
    $HeadExit = 1
}}
Write-Host "  Head test exit code: $HeadExit"
Pop-Location

# ---- Verdict ----
Write-Host ""
Write-Host "============================================================"
Write-Host "[5/5] VERDICT"
Write-Host "============================================================"
Write-Host "  Base ($BaseRef):  exit=$BaseExit"
Write-Host "  Head ($HeadRef):  exit=$HeadExit"

if ($BaseExit -eq 0 -and $HeadExit -ne 0) {{
    Write-Host ""
    Write-Host "  >> REGRESSION CONFIRMED <<"
    Write-Host "  Test passes in Base but fails in Head."
    Write-Host "  The PR introduced a breaking change."
    Write-Host ""
    Write-Host "  Finding: {description}"
}} elseif ($BaseExit -ne 0 -and $HeadExit -eq 0) {{
    Write-Host "  >> UNEXPECTED FIX <<"
    Write-Host "  Test fails in Base but passes in Head."
}} elseif ($BaseExit -ne 0 -and $HeadExit -ne 0) {{
    Write-Host "  >> AMBIGUOUS <<"
    Write-Host "  Test fails in both Base and Head."
}} else {{
    Write-Host "  >> COMPLIANT <<"
    Write-Host "  Test passes in both Base and Head."
    Write-Host "  Note: runtime test may not catch all regression types."
}}
Write-Host "============================================================"
"""
