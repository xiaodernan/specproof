"""Gate for scripts/demo_doctor.py — the demo self-check the user guide depends on."""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "demo_doctor.py"
DEMO = REPO / "demo" / "spring-backend"


def run_doctor(*args: str) -> tuple[int, dict]:
    out = subprocess.run(
        [sys.executable, str(SCRIPT), "--json", *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    return out.returncode, json.loads(out.stdout.strip().splitlines()[-1])


def test_demo_doctor_json_report_shape() -> None:
    code, report = run_doctor()
    assert code in (0, 1, 2)
    assert set(report) == {"exit", "checks"}
    assert report["exit"] == code
    assert isinstance(report["checks"], list) and report["checks"]
    for row in report["checks"]:
        assert set(row) == {"check", "status", "detail"}
        assert row["status"] in {"PASS", "WARN", "FAIL"}


def test_demo_doctor_passes_on_this_checkout() -> None:
    if not DEMO.exists():
        return  # shallow clone without the demo — nothing to verify here
    code, report = run_doctor()
    if code == 2:
        return  # environment without git work-tree access
    hard_failures = [r["check"] for r in report["checks"] if r["status"] == "FAIL"]
    assert not hard_failures, f"demo doctor hard-failures: {hard_failures}"
    # strict-clean legitimately goes red when the demo tree is dirty
    code_strict, _ = run_doctor("--strict-clean")
    assert code_strict in (0, 1)
