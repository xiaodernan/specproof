"""The court-cache lock must stay verified on every CI run.

Runs scripts/audit_court_lock.py as a black box and asserts byte-level
verdicts. If any of the four core invariants drifts, this fails BEFORE the
ledger changes (the lock is computed from tracking code, not lore).
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_court_lock_script_exits_zero_on_this_repo() -> None:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "audit_court_lock.py")],
        capture_output=True, text=True, cwd=ROOT, timeout=30, check=False, env=env,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "verdict: LOCKED" in out.stdout


def test_court_lock_json_is_locked_and_anchored() -> None:
    doc = json.loads((ROOT / "apps" / "web" / "src" / "pages" / "courtLock.json").read_text(encoding="utf-8"))
    assert doc["verdict"] == "LOCKED"
    assert len(doc["lock"]) == 16
    assert len(doc["checks"]) == 5
    for c in doc["checks"]:
        assert c["found"] is True, c["id"]
    ids = {c["id"] for c in doc["checks"]}
    assert ids == {
        "openai_compatible_stream_true",
        "openai_compatible_include_usage",
        "policy_disabled_by_default",
        "semantic_cache_evidence_kinds_match",
        "semantic_cache_cacheable_kinds_match",
    }
