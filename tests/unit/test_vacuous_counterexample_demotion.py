"""#262: a generated counterexample whose review proved it vacuous must not
carry a PASS.

The counterexample generator records ``review.checks.vacuous`` when the
generated test declares no assertion that can fail. A both-sides-green run
is then vacuous evidence — the PASS the reader would otherwise see in the
matrix is one the pipeline already disproved. This file pins, through
``run_differential_node`` itself, that:

- vacuous=True  -> the AUTH/UNIQUE contract rows are UNVERIFIED and carry
  the ``checks.vacuous`` reason on ``details``;
- vacuous=False -> PASS survives;
- absence of a review (or of ``checks``) -> PASS survives (no positive
  evidence of vacuousness, so no demotion).

Everything heavy (Maven, external stores, DB dumps, probe) is stubbed at
the module seam; the contract-results construction under test runs for
real.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import agent.nodes.run_differential as run_differential_module
from agent.nodes.run_differential import run_differential_node


def _workspaces(tmp_path: Path) -> tuple[str, str]:
    base = tmp_path / "base"
    head = tmp_path / "head"
    base.mkdir()
    head.mkdir()
    return str(base), str(head)


def _state(
    tmp_path: Path,
    generation_record: dict[str, Any],
    contracts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    base, head = _workspaces(tmp_path)
    return {
        "base_workspace": base,
        "head_workspace": head,
        "app_dir": "",
        "changed_symbols": [],
        "generation_record": generation_record,
        "contracts": contracts
        if contracts is not None
        else [
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


@pytest.fixture
def _stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        run_differential_module,
        "_run_generated_test",
        lambda *a, **kw: {
            "exit_code": 0,
            "stdout": "Tests run: 2",
            "stderr": "",
            "error": "",
            "test_counts": {"tests": 2, "failures": 0},
        },
    )
    monkeypatch.setattr(
        run_differential_module, "_inject_test_into_workspaces", lambda *a, **kw: True
    )
    monkeypatch.setattr(
        run_differential_module,
        "_capture_external_state",
        lambda *a, **kw: {
            "redis": {},
            "objects": {},
            "redis_observed": False,
            "objects_observed": False,
        },
    )
    monkeypatch.setattr(
        run_differential_module,
        "_reset_external_state",
        lambda *a, **kw: {"reset": False, "reason": "stubbed"},
    )
    monkeypatch.setattr(
        run_differential_module,
        "_capture_db_snapshot",
        lambda *a, **kw: {"method": "none", "rows": {}, "note": "stubbed"},
    )
    monkeypatch.setattr(
        run_differential_module, "_run_probe_experiment", lambda *a, **kw: []
    )
    monkeypatch.setattr(
        run_differential_module, "base_build_cache_dir", lambda *a, **kw: None
    )


def _result_by_id(out: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["contract_id"]: row for row in out["contract_results"]}


def test_vacuous_counterexample_demotes_pass_to_unverified(
    tmp_path: Path, _stubbed: None
) -> None:
    state = _state(tmp_path, {"review": {"checks": {"vacuous": True}}})

    out = run_differential_node(state)  # type: ignore[arg-type]

    rows = _result_by_id(out)
    assert set(rows) == {"AUTH-01", "UNIQUE-01"}
    for row in rows.values():
        assert row["result"] == "UNVERIFIED"
        assert row["experiment"] == "generated_test_differential"
        assert "checks.vacuous" in row["details"]


def test_sound_review_keeps_pass(tmp_path: Path, _stubbed: None) -> None:
    state = _state(tmp_path, {"review": {"checks": {"vacuous": False}}})

    out = run_differential_node(state)  # type: ignore[arg-type]

    rows = _result_by_id(out)
    assert rows["AUTH-01"]["result"] == "PASS"
    assert rows["UNIQUE-01"]["result"] == "PASS"
    # A kept PASS carries an evidence ref, never the demotion reason.
    assert rows["AUTH-01"]["evidence_ref"].startswith("sha256:")
    assert "details" not in rows["AUTH-01"]


def test_absence_of_review_keeps_pass(tmp_path: Path, _stubbed: None) -> None:
    state = _state(tmp_path, {})

    out = run_differential_node(state)  # type: ignore[arg-type]

    rows = _result_by_id(out)
    assert rows["AUTH-01"]["result"] == "PASS"
    assert rows["UNIQUE-01"]["result"] == "PASS"


def test_review_with_absent_checks_keeps_pass(tmp_path: Path, _stubbed: None) -> None:
    state = _state(tmp_path, {"review": {"checks": None}})

    out = run_differential_node(state)  # type: ignore[arg-type]

    rows = _result_by_id(out)
    assert rows["AUTH-01"]["result"] == "PASS"
    assert rows["UNIQUE-01"]["result"] == "PASS"
