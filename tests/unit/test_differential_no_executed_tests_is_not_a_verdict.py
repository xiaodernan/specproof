"""#530 — a differential that executed no tests is unjudgeable, not a verdict.

Measured shape (CI eval-golden-cases at 0ae4890, cold Maven cache): the
sandbox's offline `mvn -o test` died in dependency resolution on BOTH sides
(`DependencyResolutionException`; surefire never ran, so both runs report
`tests: 0`). The node compared the two non-zero exits and emitted
"Test fails in both Base and Head" — AMBIGUOUS, severity NONE — which reads
as "both sides behaved the same" while the generated test never executed.
The eval counted that as a judged negative (MISS), so a toolchain failure
surfaced as Recall 0.0%.

The guard: a comparison needs the generated test to have executed on both
sides. Zero tests on either side -> NON_REPRODUCIBLE (DIFF-01) with the
toolchain's own error line, which the eval maps to NOT_RUN. The last case
pins the other direction: a genuine both-sides failure (tests did run)
keeps its AMBIGUOUS split — the guard must not swallow real verdicts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from observability.metrics import snapshot


def _counter(name: str) -> float:
    return snapshot()["counters"].get(name, 0.0)


def _result(
    exit_code: int,
    tests: int,
    *,
    failures: int = 0,
    stdout: str = "",
) -> dict[str, Any]:
    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": "",
        "test_counts": {
            "tests": tests, "failures": failures, "errors": 0, "skipped": 0,
        },
        "error": "",
    }


def _stub_execution(
    monkeypatch: pytest.MonkeyPatch, results: dict[str, Any]
) -> None:
    def fake(job_id: object, stage: str, fn: object, *args: object, **kwargs: object) -> Any:  # noqa: ARG001
        return results[stage]

    monkeypatch.setattr(
        "agent.nodes.run_differential.run_with_cancel_checks", fake
    )


def _make_state(tmp_path: Path) -> dict[str, Any]:
    base_ws = tmp_path / "base"
    head_ws = tmp_path / "head"
    base_ws.mkdir()
    head_ws.mkdir()
    gen = tmp_path / "SpecProofGeneratedTest.java"
    gen.write_text("class SpecProofGeneratedTest {}\n", encoding="utf-8")
    return {
        "repo_path": "",
        "app_dir": "",
        "base_workspace": str(base_ws),
        "head_workspace": str(head_ws),
        "generated_tests_path": str(gen),
        "contracts": [{"id": "UNIQUE-01"}],
    }


_OFFLINE_ERROR = (
    "[ERROR] Cannot access central (https://repo.maven.apache.org/maven2) "
    "in offline mode and the artifact io.netty:netty-common:jar:4.1.118.Final "
    "has not been downloaded from it before."
)


def test_both_sides_failed_before_running_any_test_is_not_ambiguous(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    from agent.nodes.run_differential import run_differential_node

    before_errors = _counter("differential_errors_total")
    before_ambiguous = _counter("differential_outcomes_ambiguous_total")

    _stub_execution(monkeypatch, {
        "maven_base": _result(1, 0, stdout=_OFFLINE_ERROR),
        "maven_head": _result(1, 0, stdout=_OFFLINE_ERROR),
        "maven_probe": [],
    })
    out = run_differential_node(_make_state(tmp_path))

    entry = out["diff_results"][0]
    assert entry["verdict"] == "NON_REPRODUCIBLE", (
        "zero executed tests on both sides is a toolchain failure, not a "
        f"behavioral verdict; got {entry['verdict']}: {entry['detail']}"
    )
    assert "executed no tests" in entry["detail"]
    assert entry["base_test_counts"]["tests"] == 0
    assert entry["head_test_counts"]["tests"] == 0
    assert _OFFLINE_ERROR[:60] in entry["detail"], (
        "the entry must name the toolchain error itself, not just counts"
    )
    assert _counter("differential_errors_total") == before_errors + 1
    assert _counter("differential_outcomes_ambiguous_total") == before_ambiguous, (
        "an unexecuted run must not be counted as an ambiguous test outcome"
    )
    assert [r["result"] for r in out["contract_results"]] == ["UNVERIFIED"], (
        "the contract the test was meant to verify is UNVERIFIED with the "
        "reason, not silently absent or PASS"
    )
    assert "executed no tests" in out["contract_results"][0]["details"]


def test_a_vacuous_pass_side_cannot_carry_a_regression(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Base exited 0 without running a test: its "pass" is empty evidence.

    Comparing it to a failing Head would emit REGRESSION on a side that
    never executed the generated test. The comparison is unjudgeable.
    """
    from agent.nodes.run_differential import run_differential_node

    _stub_execution(monkeypatch, {
        "maven_base": _result(0, 0),
        "maven_head": _result(1, 4, failures=4),
        "maven_probe": [],
    })
    out = run_differential_node(_make_state(tmp_path))

    entry = out["diff_results"][0]
    assert entry["verdict"] == "NON_REPRODUCIBLE", (
        f"a zero-test base run cannot witness a regression; got {entry['verdict']}"
    )
    assert "base tests: 0" in entry["detail"]


def test_a_real_both_sides_failure_keeps_its_ambiguous_verdict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """Reverse control: when tests DID run on both sides, nothing changes."""
    from agent.nodes.run_differential import run_differential_node

    _stub_execution(monkeypatch, {
        "maven_base": _result(1, 4, failures=1),
        "maven_head": _result(1, 4, failures=1),
        "maven_probe": [],
    })
    out = run_differential_node(_make_state(tmp_path))

    entry = out["diff_results"][0]
    assert entry["verdict"] == "AMBIGUOUS", (
        "a genuine both-sides test failure must keep the split/ambiguous "
        f"verdict; got {entry['verdict']}: {entry['detail']}"
    )
    assert entry["base_test_counts"]["tests"] == 4
