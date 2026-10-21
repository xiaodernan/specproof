
"""create_capsule node — package Bug Capsules for BLOCKER/MAJOR findings.

Counters (#200): ``create_capsule_runs_total`` counts every invocation and
``create_capsule_outcomes_<word>_total`` records how the attempt ended —
``packed`` (>=1 capsule written), ``no_findings`` (no confirmed findings
at all) or ``filtered_out`` (findings exist but every one is below the
BLOCKER/MAJOR packaging threshold). The last two both return an empty
capsules list; the word is the countable difference between "nothing was
found" and "everything was filtered". Capsule metadata recording stays
best-effort (logged, no counter — the documented gap shared with
publish_report's lineage plumbing).
"""
import hashlib
import json
import os
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.state import Phase0State
from observability.metrics import incr

#: The closed set of ways a capsule-packing run can end (#200). Mirrored by
#: the parity family's regex and the behavior tests — a new word must move
#: all three together.
CREATE_CAPSULE_OUTCOMES = frozenset({
    "packed",          # >=1 capsule zip written
    "no_findings",     # confirmed findings list empty
    "filtered_out",    # findings exist, all below BLOCKER/MAJOR
})


def _inflight_evidence_md(finding: dict[str, Any]) -> str:
    """Render a README section for the in-flight evidence run_differential
    captures (#250/#253/#254), so a capsule reproduction explains *why* the
    finding stands even when the post-run H2 dump reads DB_CONSISTENT (the
    scaffold rolled the committed transaction back, or a later ``@BeforeEach``
    wiped the row). The head-side generated test's head-only DB-state-violation
    assertion is that captured evidence.

    Capture-only: this renders what was recorded; it changes no verdict. Returns
    "" when nothing was captured.
    """
    parts: list[str] = []
    detail = str(finding.get("db_state_detail") or "")
    if detail:
        parts.append(f"**DB state:** {detail}")
    dbv = finding.get("db_violation_evidence")
    if isinstance(dbv, dict) and dbv.get("head_observed"):
        head_only = " (head-only)" if dbv.get("head_only") else ""
        parts.append(
            "**In-flight DB-state violation:** the head-side generated test "
            f"asserted `{dbv.get('marker', 'DB STATE VIOLATION')}`{head_only} "
            "at the moment it observed the mutated state — evidence the "
            "post-run dump cannot see when the effect was rolled back or wiped."
        )
    beh = finding.get("behavioral_evidence")
    if isinstance(beh, dict) and beh.get("captured"):
        parts.append(f"**Behavioral evidence:** {beh.get('note', '')}")
    if not parts:
        return ""
    return "## In-flight Evidence\n" + "\n\n".join(parts) + "\n\n"


def create_capsule_node(state: Phase0State) -> dict[str, Any]:
    """Create Bug Capsule zip files for each confirmed finding.

    Each capsule contains manifest, requirement, contract, finding,
    generated tests, fixtures, and a run.sh script.
    """
    confirmed_findings = state.get("confirmed_findings", [])
    contracts = state.get("contracts", [])
    requirement_text = state.get("requirement_text", "")
    generated_tests_path = state.get("generated_tests_path", "")
    capsules: list[str] = []
    #: The object-store coordinates of the capsules ("bucket/object-name")
    #: — where the bytes ARE, not where the local file was.
    capsule_refs: list[str] = []

    incr("create_capsule_runs_total")
    output_dir = Path("capsules")
    output_dir.mkdir(parents=True, exist_ok=True)

    for finding in confirmed_findings:
        if finding.get("severity") not in ("BLOCKER", "MAJOR"):
            continue

        fid = finding.get("id", str(uuid.uuid4())[:8])
        capsule_dir = output_dir / f"capsule-{fid}"
        capsule_dir.mkdir(parents=True, exist_ok=True)

        # manifest.json (P0.5: evidence_digest, never "signature")
        _dbv = finding.get("db_violation_evidence")
        _beh = finding.get("behavioral_evidence")
        manifest = {
            "finding_id": fid,
            "severity": finding.get("severity"),
            "confidence": finding.get("confidence"),
            "created_at": datetime.now(UTC).isoformat(),
            "contract_id": finding.get("contract_id"),
            "evidence_type": finding.get("evidence_type"),
            "evidence_digest": finding.get("evidence_digest", ""),
            "db_state_verdict": finding.get("db_state_verdict", ""),
            "blocker_check": finding.get("blocker_check", {}),
            # #261/#267: surface the in-flight evidence run_differential captures
            # (#250/#253/#254) in the restatable capsule manifest, so a replay
            # states *why* the finding stands even when the post-run H2 dump
            # reads DB_CONSISTENT (the scaffold rolled/wiped the committed row)
            # — the head-side generated test's head-only DB-state-violation
            # assertion is the captured evidence. Structured dicts kept verbatim;
            # a non-dict value becomes {}.
            "db_state_detail": finding.get("db_state_detail", ""),
            "db_violation_evidence": dict(_dbv) if isinstance(_dbv, dict) else {},
            "behavioral_evidence": dict(_beh) if isinstance(_beh, dict) else {},
        }
        # The digest is computed over the CANONICAL serialization of the
        # manifest WITHOUT the digest field (sorted keys, no whitespace) —
        # verifiable by re-serializing any stored copy the same way.
        canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
        manifest_digest = hashlib.sha256(canonical.encode()).hexdigest()
        manifest["manifest_digest"] = f"sha256:{manifest_digest}"
        (capsule_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

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
        (capsule_dir / "finding.json").write_text(
            json.dumps(finding, indent=2), encoding="utf-8"
        )

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
            "LLM_API_KEY=replace_me\n"
            "MYSQL_PASSWORD=replace_me\n"
            "REDIS_PASSWORD=replace_me\n"
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
            f"{_inflight_evidence_md(finding)}"
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

        # §A task 7: the capsule becomes locatable through the object
        # metadata store (query by job_id / kind / digest / contract_id)
        # instead of path inference. Recording is best-effort: a capsule
        # that cannot be recorded stays a legacy path-based artifact.
        _record_capsule_metadata(
            zip_path=zip_path,
            job_id=str(state.get("job_id") or ""),
            contract_id=str(finding.get("contract_id") or ""),
        )

        # The capsule also goes to the OBJECT STORE, and its coordinate
        # comes back. Without this the object store is never written by
        # the pipeline at all: the bytes live on a local disk, the
        # evidence chain has no address for them, and every "where is
        # this artifact" question can only be answered by guessing a
        # path. The upload is best-effort (a store that is down must not
        # cost us the capsule) but it is NOT silent — the outcome is
        # counted and the coordinate travels in the state either way.
        coordinate = _upload_capsule(
            zip_path=zip_path,
            finding_id=fid,
            job_id=str(state.get("job_id") or ""),
        )
        if coordinate:
            capsule_refs.append(coordinate)

    if capsules:
        incr("create_capsule_outcomes_packed_total")
    elif not confirmed_findings:
        incr("create_capsule_outcomes_no_findings_total")
    else:
        incr("create_capsule_outcomes_filtered_out_total")

    return {"capsules": capsules, "capsule_refs": capsule_refs}


def _upload_capsule(
    zip_path: Path, finding_id: str, job_id: str,
) -> str:
    """Upload the capsule to the object store; return its coordinate.

    The coordinate is "bucket/object-name" — where the bytes ARE. A
    local path is where the file WAS, on the machine that made it.

    Best effort, but never silent: a store that is down leaves the
    capsule a local artifact and the coordinate empty, and both outcomes
    are counted. A capsule whose upload failed is not a lost capsule —
    the zip is still on disk — but the evidence chain cannot point at
    it, and the counters have to say so.
    """
    try:
        from storage.minio import MinIOClient
    except Exception:  # noqa: BLE001 — the driver is optional
        incr("create_capsule_upload_unavailable_total")
        return ""
    try:
        client = MinIOClient()
        bucket = "specproof-bug-capsules"
        name = f"jobs/{job_id or 'unknown'}/capsule-{finding_id}.zip"
        uploaded = client.put_object_with_digest(
            bucket, name, zip_path.read_bytes(),
            content_type="application/zip",
        )
        coordinate = (
            f"{uploaded.get('bucket') or bucket}/"
            f"{uploaded.get('object_name') or name}"
        )
        incr("create_capsule_upload_succeeded_total")
        return coordinate
    except Exception as exc:  # noqa: BLE001 — the capsule survives locally
        import logging

        logging.getLogger(__name__).warning(
            "capsule upload failed (%s: %s) — the capsule stays a local "
            "artifact and the evidence chain cannot address it",
            type(exc).__name__, exc,
        )
        incr("create_capsule_upload_failed_total")
        return ""


def _record_capsule_metadata(
    zip_path: Path, job_id: str, contract_id: str,
) -> None:
    """Record capsule object metadata (best effort, never breaks the node)."""
    try:
        from storage.object_metadata import record_file_object_best_effort

        record_file_object_best_effort(
            "capsule",
            zip_path,
            job_id=job_id,
            contract_ids=(contract_id,) if contract_id else (),
        )
    except Exception:  # noqa: BLE001 — artifact writing must never break
        import logging

        logging.getLogger(__name__).warning(
            "capsule metadata record failed for %s", zip_path
        )


def _build_replay_script(
    fid: str,
    finding: dict[str, Any],
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
        return _build_ps1_script(fid, severity, contract_id, description,
                                 evidence_type, capsule_dir_name)
    else:
        return _build_sh_script(fid, severity, contract_id, description,
                                evidence_type, capsule_dir_name)


def _build_sh_script(
    fid: str, severity: str, contract_id: str, description: str,
    evidence_type: str, capsule_dir_name: str,
) -> str:
    """Build a bash replay script."""
    return f'''#!/bin/bash
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
    # Copy test files into the repo's Maven test source root
    # (src/test/java) so Maven actually compiles and runs them.
    TEST_DEST="$REPO_DIR/src/test/java"
    mkdir -p "$TEST_DEST" 2>/dev/null || true
    if [ -d "$TEST_DEST" ]; then
        cp -r "$TEST_SRC"/* "$TEST_DEST/" 2>/dev/null || true
        echo "  Tests copied to $TEST_DEST"
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
'''


def _build_ps1_script(
    fid: str, severity: str, contract_id: str, description: str,
    evidence_type: str, capsule_dir_name: str,
) -> str:
    """Build a PowerShell replay script for Windows."""
    return f'''# ============================================================
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
    $destDir = "$RepoDir\\src\\test\\java"
    if (-not (Test-Path $destDir)) {{
        New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    }}
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
'''
