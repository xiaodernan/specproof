"""The contract list and the matrix must not disagree about the same contract.

A real `specproof demo --run` (#511) printed, in one run:

    [+] TOKEN_INVALIDATION-01 (redis) -> PASS          ← contract list
    Matrix: 6 rows | +4 passed | -1 failed | ?1 unverified   ← the same run
    … TOKEN_INVALIDATION-01：… 此通过不能作为验收依据      ← verdict reason
    (report table row) TOKEN_INVALIDATION-01 … UNVERIFIED

The list was printing the **check-level** result while the verdict, the HTML
report and the matrix summary all count the **row-level** result, which is where
a passing check is downgraded to UNVERIFIED when the evidence does not reach the
required level. Same contract, two answers — and the reassuring one came first.

The fix keeps both facts and leads with the authoritative one:
`[?] TOKEN_INVALIDATION-01 (redis) -> UNVERIFIED  (检查本身 PASS；<reason>)`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from cli.specproof.commands.verify import verify


def _state(*, matrix_result: str, check_result: str) -> dict[str, Any]:
    row: dict[str, Any] = {
        "contract_id": "C-1",
        "result": matrix_result,
        "evidence_refs": ["ev-1"] if matrix_result == "PASS" else [],
        "experiment_ids": ["DIFF-01"],
    }
    if matrix_result == "UNVERIFIED":
        row["unverified_reason"] = "外部观测面未被观测（存储不可达或两个时刻不可比）"
    return {
        "matrix": {
            "rows": [row],
            "total_contracts": 1,
            "passed": 1 if matrix_result == "PASS" else 0,
            "failed": 1 if matrix_result == "FAIL" else 0,
            "unverified": 1 if matrix_result == "UNVERIFIED" else 0,
            "total_rows": 1,
        },
        "contracts": [{"id": "C-1", "checker_type": "redis"}],
        "contract_results": [{"contract_id": "C-1", "result": check_result}],
        "confirmed_findings": [],
        "errors": [],
        "capsules": [],
        "release_results": {},
    }


@pytest.fixture()
def run_with_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    holder: dict[str, dict[str, Any]] = {}

    class _FakeGraph:
        def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
            return holder["state"]

    monkeypatch.setattr("agent.graph.build_phase0_graph", lambda: _FakeGraph())
    monkeypatch.setattr("agent.preflight.detect_language", lambda *_a, **_k: "python")
    monkeypatch.setattr(
        "agent.preflight.run_preflight",
        lambda *_a, **_k: type("P", (), {"passed": True})(),
    )
    monkeypatch.setattr(
        "agent.preflight.format_preflight_report", lambda *_a, **_k: "preflight ok"
    )

    def _run(state: dict[str, Any]) -> Any:
        holder["state"] = state
        spec = tmp_path / "spec.txt"
        spec.write_text("要求: 邮箱变更需要认证\n", encoding="utf-8")
        return CliRunner().invoke(verify, [
            "--repo", str(tmp_path),
            "--base", "base", "--head", "head",
            "--spec", str(spec),
            "--output-dir", str(tmp_path / "out"),
            "--no-llm",
        ])

    return _run


def test_a_downgraded_contract_is_not_printed_as_pass(run_with_state) -> None:
    result = run_with_state(_state(matrix_result="UNVERIFIED", check_result="PASS"))

    assert "C-1 (redis) -> UNVERIFIED" in result.output, (
        "the list must lead with the matrix result, which is what the verdict "
        "and the report use; output was:\n" + result.output
    )
    assert "-> PASS" not in result.output, (
        "a contract the matrix counts as unverified must not read as PASS"
    )


def test_the_check_result_and_the_reason_stay_visible(run_with_state) -> None:
    result = run_with_state(_state(matrix_result="UNVERIFIED", check_result="PASS"))

    assert "检查本身 PASS" in result.output, (
        "the check really did pass; dropping that fact would be the opposite error"
    )
    assert "外部观测面未被观测" in result.output, "the downgrade reason must be printed"


def test_agreeing_results_print_one_plain_line(run_with_state) -> None:
    result = run_with_state(_state(matrix_result="PASS", check_result="PASS"))

    assert "C-1 (redis) -> PASS" in result.output
    assert "检查本身" not in result.output, (
        "when the two agree there is nothing to explain"
    )
