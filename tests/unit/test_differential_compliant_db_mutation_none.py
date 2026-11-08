"""End-to-end test of ``run_differential_node`` on COMPLIANT + DB_MUTATED_ON_UNAUTH.

base passes and head passes (HTTP verdict COMPLIANT), but the real H2 dumps
differ. Per the combined-verdict rule this does NOT become BLOCKER: an HTTP
compliant run is not a regression, and a DB difference without an HTTP
regression is not attributable to the head as a behavior defect. The entry
stays COMPLIANT / severity NONE / confidence 0.80, and contract_results
stays PASS (the counterexample can fail — generation_record has no vacuous
review — so both contracts pass).

Same seam stubs as #592/#593/#595; only the run outcomes and db verdict differ.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent.nodes import run_differential as rd

BASE_APP = "/tmp/sp/base"
HEAD_APP = "/tmp/sp/head"

DB_SNAPSHOT: dict[str, Any] = {
    "method": "h2_file_dump",
    "rows": {"users:1": "a@x", "products:1": "p1"},
    "tables": {"users": [{"id": "1", "email": "a@x"}]},
    "note": "",
}


def _state() -> dict[str, Any]:
    return {
        "base_workspace": BASE_APP,
        "head_workspace": HEAD_APP,
        "app_dir": "",
        "changed_symbols": ["AuthController", "UserService"],
        "generation_record": {},
        "contracts": [
            {
                "id": "AUTH-01",
                "version": 1,
                "requirement": "未认证请求必须返回 401",
                "checker_type": "http",
            },
            {
                "id": "UNIQUE-01",
                "version": 3,
                "requirement": "邮箱唯一",
                "checker_type": "sql",
            },
        ],
        "generated_tests_path": "SpecProofGeneratedTest.java",
        "job_id": None,
    }


def _patch(monkeypatch: pytest.MonkeyPatch) -> None:
    def generated_test(workspace: str, test_class: str, skip_main: bool = False) -> dict[str, Any]:
        return {
            "exit_code": 0,
            "stdout": "Tests run: 3, Failures: 0",
            "stderr": "",
            "error": "",
            "test_counts": {"tests": 3, "failures": 0},
        }

    monkeypatch.setattr(rd, "_run_generated_test", generated_test)
    monkeypatch.setattr(rd, "_inject_test_into_workspaces", lambda *a, **k: True)
    monkeypatch.setattr(rd, "base_build_cache_dir", lambda *a, **k: None)
    monkeypatch.setattr(
        rd,
        "_capture_external_state",
        lambda *a, **k: {
            "redis": {},
            "objects": {},
            "redis_observed": False,
            "objects_observed": False,
        },
    )
    monkeypatch.setattr(
        rd, "_reset_external_state", lambda *a, **k: {"reset": False, "reason": "stubbed"}
    )
    monkeypatch.setattr(rd, "_capture_db_snapshot", lambda *a, **k: dict(DB_SNAPSHOT))
    monkeypatch.setattr(
        rd,
        "_compare_db_state",
        lambda base, head: ("DB_MUTATED_ON_UNAUTH", "users table differs"),
    )
    monkeypatch.setattr(rd, "_test_failure_details", lambda *a, **k: {})
    monkeypatch.setattr(
        rd,
        "_failing_test_name",
        lambda *a, **k: "duplicateEmailChangeMustBeRejected",
    )
    monkeypatch.setattr(rd, "_run_probe_experiment", lambda *a, **k: [])
    monkeypatch.setattr(rd, "_check_http_diff", lambda *a, **k: [])


def test_compliant_with_db_mutation_stays_compliant_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch(monkeypatch)

    out = rd.run_differential_node(_state())  # type: ignore[arg-type]

    # ── diff_results: COMPLIANT, NONE severity, 0.80 confidence ───────────
    primary = [d for d in out["diff_results"] if d.get("experiment_id") == "DIFF-01"]
    assert len(primary) == 1
    entry = primary[0]
    assert entry["contract_id"] == "AUTH-01"  # default attribution when no head failure
    assert entry["verdict"] == "COMPLIANT"
    assert entry["severity"] == "NONE"
    assert entry["confidence"] == 0.80
    assert entry["evidence_type"] == "differential_execution"
    assert entry["base_exit_code"] == 0
    assert entry["head_exit_code"] == 0
    assert entry["db_state_verdict"] == "DB_MUTATED_ON_UNAUTH"
    assert entry["detail"] == "Test passes in both Base and Head"
    # The DB mutation is recorded per-side but does not upgrade a compliant
    # HTTP verdict into BLOCKER.

    # ── contract_results: PASS both, no mutation-derived FAIL ─────────────
    results = {row["contract_id"]: row for row in out["contract_results"]}
    assert set(results) == {"AUTH-01", "UNIQUE-01"}
    assert results["AUTH-01"]["result"] == "PASS"
    assert results["UNIQUE-01"]["result"] == "PASS"
    assert results["AUTH-01"]["experiment"] == "generated_test_differential"
    assert results["UNIQUE-01"]["experiment"] == "generated_test_differential"
