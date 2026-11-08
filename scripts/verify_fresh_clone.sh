#!/usr/bin/env bash
# scripts/verify_fresh_clone.sh — reproduce the fresh-clone onboarding check.
#
# What it verifies (read-only against the remote; nothing is written to this repo):
#   1. a full clone of origin/master carries the SAME file set with the SAME
#      blob SHAs as this checkout (git ls-tree -r HEAD on both sides;
#      any mismatch in name or object id fails the check);
#   2. `pip install -e ".[dev]"` succeeds on the clone with Python 3.12 and
#      `specproof --help` / `specproof quickstart` render;
#   3. the offline gate subset passes on the clone (backup_stores 16,
#      production_services_do_not_run_as_root 7, subprocess_text_encoding 4,
#      alertmanager_config_is_wired 7 — 34 tests);
#   4. the ledger fence passes on the clone (>= 100 reachable revisions —
#      a --depth 1 clone refuses by design with UnreadableLedgerError, which
#      is the fence being honest, not broken).
#
# Requirements: git, and SPECPROOF_PYTHON pointing at a Python 3.12
# interpreter (e.g. the interpreter inside your own .venv), else `python3`.
# Example:
#   SPECPROOF_PYTHON=.venv/Scripts/python scripts/verify_fresh_clone.sh
# Exits non-zero on any mismatch; prints a report at the end.
#
# NOTE: does NOT run the full suite on the clone (it shares the specproof_test
# MySQL isolation and would contend with other lanes); full-suite evidence is
# collected in the CI job `tests-no-infra` and the ledger.

set -eu

REPO_URL="https://github.com/xiaodernan/specproof.git"
PY="${SPECPROOF_PYTHON:-python3}"
WORK_DIR="${1:-$(mktemp -d)}"
CLONE_DIR="$WORK_DIR/specproof-fresh"
SELF_ROOT=$(git rev-parse --show-toplevel)

echo "[1/4] cloning origin/master (full history) -> $CLONE_DIR"
mkdir -p "$WORK_DIR"
git clone --single-branch --branch master "$REPO_URL" "$CLONE_DIR"

echo "[2/4] file-set + blob SHA equality between worktree HEAD and clone HEAD"
WT_TREE=$(git -C "$SELF_ROOT" ls-tree -r HEAD | LC_ALL=C sort)
CL_TREE=$(git -C "$CLONE_DIR" ls-tree -r HEAD | LC_ALL=C sort)
if [ "$WT_TREE" = "$CL_TREE" ]; then
  echo "  tree identical: $(git -C "$SELF_ROOT" ls-tree -r HEAD | wc -l) entries"
else
  echo "  TREE MISMATCH (only names or blob SHAs that differ):"
  diff <(printf '%s\n' "$WT_TREE") <(printf '%s\n' "$CL_TREE") | head -20
  exit 1
fi

echo "[3/4] install + console script on the clone (SPECPROOF_PYTHON=$PY)"
"$PY" -m venv "$CLONE_DIR/.venv"
(cd "$CLONE_DIR" && .venv/bin/python -m pip install --quiet -e .[dev])
"$CLONE_DIR/.venv/bin/specproof" --help >/dev/null && echo "  specproof --help OK"
"$CLONE_DIR/.venv/bin/specproof" quickstart >/dev/null && echo "  specproof quickstart OK"

echo "[4/4] offline gate subset + ledger fence on the clone"
cd "$CLONE_DIR"
.venv/bin/python -m pytest -q \
  tests/unit/test_backup_stores.py \
  tests/unit/test_production_services_do_not_run_as_root.py \
  tests/unit/test_subprocess_text_encoding.py \
  tests/unit/test_alertmanager_config_is_wired.py \
  tests/unit/test_recorded_ledger_sections_do_not_vanish.py

echo "FRESH-CLONE VERIFY: OK (evidence dir: $WORK_DIR)"
