#!/bin/bash
set -euo pipefail

# ============================================================
# SpecProof Bug Capsule Replay — STATIC-AUTH-01
# Severity: MAJOR
# Contract: AUTH-01
# ============================================================

REPO_DIR="${1:-$SPECPROOF_REPO}"
if [ -z "$REPO_DIR" ]; then
    echo "Usage: bash run.sh <path-to-git-repo>"
    echo "  or set SPECPROOF_REPO environment variable"
    echo ""
    echo "This script replays the differential test that detected"
    echo "the regression reported in finding STATIC-AUTH-01."
    echo "  Severity: MAJOR"
    echo "  Contract: AUTH-01"
    echo "  Evidence: static_regex_analysis"
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
echo " Finding:    STATIC-AUTH-01"
echo " Severity:   MAJOR"
echo " Contract:   AUTH-01"
echo " Evidence:   static_regex_analysis"
echo " Repo:       $REPO_DIR"
echo " Base ref:   $BASE_REF"
echo " Head ref:   $HEAD_REF"
echo "------------------------------------------------------------"
echo " Description: @PreAuthorize removed from controller method — requires differential execution to confirm regression"
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
git checkout "$BASE_REF" --quiet 2>/dev/null || {
    echo "ERROR: Cannot checkout base ref '$BASE_REF'"
    exit 1
}

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
git checkout "$HEAD_REF" --quiet 2>/dev/null || {
    echo "ERROR: Cannot checkout head ref '$HEAD_REF'"
    exit 1
}

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
    echo "  Finding: @PreAuthorize removed from controller method — requires differential execution to confirm regression"
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
