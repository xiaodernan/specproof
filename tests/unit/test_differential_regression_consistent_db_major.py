"""End-to-end test of ``run_differential_node`` on REGRESSION + DB_CONSISTENT
— the MAJOR sibling of #592's BLOCKER path.

base_pass / head_fail, but the real H2 dumps are identical (the head-side
generated test's assertion failure rolled the transaction back). Per ADR-004
condition 4, captured DB behavior evidence cannot be met from the rolled-back
dump, so the finding is honestly capped at MAJOR with confidence 0.88 — never
laundered into BLOCKER.

Same seam stubs as #592; only `_compare_db_state` differs.
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
        exit_code = 0 if workspace == BASE_APP else 1
        return {
            "exit_code": exit_code,
            "stdout": f"Tests run: 3, Failures: {0 if exit_code == 0 else 1}",
            "stderr": "",
            "error": "",
            "test_counts": {"tests": 3, "failures": 0 if exit_code == 0 else 1},
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
        lambda base, head: ("DB_CONSISTENT", "Base and Head DB dumps are identical"),
    )
    monkeypatch.setattr(rd, "_test_failure_details", lambda *a, **k: {})
    monkeypatch.setattr(
        rd,
        "_failing_test_name",
        lambda *a, **k: "duplicateEmailChangeMustBeRejected",
    )
    monkeypatch.setattr(rd, "_run_probe_experiment", lambda *a, **k: [])
    monkeypatch.setattr(rd, "_check_http_diff", lambda *a, **k: [])


def test_regression_with_consistent_db_is_major_not_blocker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch(monkeypatch)

    out = rd.run_differential_node(_state())  # type: ignore[arg-type]

    # ── diff_results: REGRESSION + DB_CONSISTENT → MAJOR ──────────────────
    primary = [d for d in out["diff_results"] if d.get("experiment_id") == "DIFF-01"]
    assert len(primary) == 1
    entry = primary[0]
    assert entry["contract_id"] == "UNIQUE-01"  # head failing test's family
    assert entry["verdict"] == "REGRESSION"
    assert entry["severity"] == "MAJOR"          # capped: no captured DB mutation
    assert entry["confidence"] == 0.88           # below BLOCKER's 0.95
    assert entry["evidence_type"] == "base_pass_head_fail"
    assert entry["db_state_verdict"] == "DB_CONSISTENT"
    assert entry["base_exit_code"] == 0
    assert entry["head_exit_code"] == 1

    # ── contract_results: attributed FAIL, others UNVERIFIED ──────────────
    results = {row["contract_id"]: row for row in out["contract_results"]}
    assert set(results) == {"AUTH-01", "UNIQUE-01"}
    assert results["UNIQUE-01"]["result"] == "FAIL"
    assert results["UNIQUE-01"]["experiment"] == "generated_test_differential"
    assert results["AUTH-01"]["result"] == "UNVERIFIED"
