"""End-to-end test of ``run_differential_node`` on the AMBIGUOUS path:
base fails and head fails, with no per-method surefire results available
(both-side whole-run collapse).

This is the masked case roadmap §2/#557 warns about: a collapsed whole-run
AMBIGUOUS (severity NONE) hides which side introduced the failure. The node
records AMBIGUOUS with confidence 0.80 and names every compiled contract as
UNVERIFIED — never laundered into a pass, never attributed to head without
per-method evidence.

Same seam stubs as #592–#597; both runs exit non-zero with executed tests,
and no surefire reports exist so the both-fail split returns None.
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
    "rows": {},
    "tables": {},
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
            "exit_code": 1,
            "stdout": "Tests run: 3, Failures: 3",
            "stderr": "",
            "error": "",
            "test_counts": {"tests": 3, "failures": 3},
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
        lambda *a, **k: "",
    )
    monkeypatch.setattr(rd, "_run_probe_experiment", lambda *a, **k: [])
    monkeypatch.setattr(rd, "_check_http_diff", lambda *a, **k: [])


def test_ambiguous_both_fail_without_per_method_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch(monkeypatch)

    out = rd.run_differential_node(_state())  # type: ignore[arg-type]

    # ── diff_results: AMBIGUOUS, NONE severity, 0.80 confidence ───────────
    primary = [d for d in out["diff_results"] if d.get("experiment_id") == "DIFF-01"]
    assert len(primary) == 1
    entry = primary[0]
    assert entry["verdict"] == "AMBIGUOUS"
    assert entry["severity"] == "NONE"
    assert entry["confidence"] == 0.80
    assert entry["evidence_type"] == "differential_execution"
    assert entry["base_exit_code"] == 1
    assert entry["head_exit_code"] == 1
    assert "Test fails in both Base and Head" in entry["detail"]

    # ── contract_results: every compiled contract UNVERIFIED ──────────────
    # No per-method evidence ⇒ nothing attributable to head.
    results = {row["contract_id"]: row for row in out["contract_results"]}
    assert set(results) == {"AUTH-01", "UNIQUE-01"}
    assert results["AUTH-01"]["result"] == "UNVERIFIED"
    assert results["UNIQUE-01"]["result"] == "UNVERIFIED"
    assert results["AUTH-01"]["experiment"] == "generated_test_differential"
    assert results["UNIQUE-01"]["experiment"] == "generated_test_differential"
