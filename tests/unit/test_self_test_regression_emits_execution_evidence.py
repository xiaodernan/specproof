"""`_self_test_differential_entry` now emits the Java lane's two-word evidence
vocabulary when both sides actually executed (#2.1 follow-up).

The Java differential's REGRESSION entry is `evidence_type: base_pass_head_fail`
(machine-readable "head introduced the failing test"), and the Review Court reads
exactly that word + recorded exits as real execution evidence
(`_has_real_execution_evidence`). The self-test path used to keep the weaker
`self_test_diff` label — correct until exits were captured, but after that it
would have hidden genuinely-executed regressions from the court.

Contract pinned here:

1. REGRESSION + both exits recorded -> `base_pass_head_fail`, MAJOR / 0.88
   (mirrors the Java lane's MAJOR review), exits recorded verbatim;
2. UNEXPECTED_FIX / COMPLIANT -> `differential_execution`, NONE / 0.80;
3. AMBIGUOUS -> `differential_execution`, NONE / 0.65;
4. exit code missing on either side -> `self_test_diff`, no severity
   (an adapter that never captured an exit carries no evidence claim);
5. The court's `_has_real_execution_evidence` accepts the entry from (1).
"""

from __future__ import annotations

import pytest

from agent.nodes import run_differential as rd
from agent.review_court import policy

BASE_OK = {"ok": True, "counts": {"passed": 10, "failed": 0, "errors": 0},
           "mode": "docker", "error": "", "exit_code": 0}
HEAD_RED = {"ok": True, "counts": {"passed": 9, "failed": 1, "errors": 0},
            "mode": "docker", "error": "", "exit_code": 1}


def _runs(monkeypatch, base: dict, head: dict) -> None:
    seq = iter([base, head])
    monkeypatch.setattr(rd, "run_with_cancel_checks",
                        lambda *a, **k: next(seq))


def test_regression_with_recorded_exits_speaks_the_java_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _runs(monkeypatch, dict(BASE_OK), dict(HEAD_RED))
    entry = rd._self_test_differential_entry({}, "/base", "/head", "python")

    assert entry["verdict"] == "REGRESSION"
    assert entry["evidence_type"] == "base_pass_head_fail"
    assert entry["base_exit_code"] == 0
    assert entry["head_exit_code"] == 1
    assert entry["severity"] == "MAJOR"
    assert entry["confidence"] == 0.88
    assert policy._has_real_execution_evidence([entry]) is True


def test_unexpected_fix_and_compliant_degrade_to_differential_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base_red = dict(BASE_OK, counts={"passed": 8, "failed": 1, "errors": 0}, exit_code=1)
    head_ok = dict(HEAD_RED, counts={"passed": 10, "failed": 0, "errors": 0}, exit_code=0)
    _runs(monkeypatch, base_red, head_ok)
    entry = rd._self_test_differential_entry({}, "/base", "/head", "python")
    assert entry["verdict"] == "UNEXPECTED_FIX"
    assert entry["evidence_type"] == "differential_execution"
    assert entry["severity"] == "NONE"

    _runs(monkeypatch, dict(BASE_OK), dict(BASE_OK))
    entry = rd._self_test_differential_entry({}, "/base", "/head", "python")
    assert entry["verdict"] == "COMPLIANT"
    assert entry["evidence_type"] == "differential_execution"
    assert entry["severity"] == "NONE"


def test_ambiguous_is_differential_execution_not_a_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    both_red = dict(HEAD_RED)
    _runs(monkeypatch, dict(BASE_OK, counts=both_red["counts"], exit_code=1), dict(HEAD_RED))
    entry = rd._self_test_differential_entry({}, "/base", "/head", "python")
    assert entry["verdict"] == "AMBIGUOUS"
    assert entry["evidence_type"] == "differential_execution"
    assert entry["severity"] == "NONE"
    assert entry["confidence"] == 0.65


def test_missing_exit_codes_keep_self_test_diff_and_no_severity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = {"ok": True, "counts": dict(BASE_OK["counts"]), "mode": "docker", "error": ""}
    head = {"ok": True, "counts": dict(HEAD_RED["counts"]), "mode": "docker", "error": ""}
    _runs(monkeypatch, base, head)
    entry = rd._self_test_differential_entry({}, "/base", "/head", "python")

    assert entry["verdict"] == "REGRESSION"
    assert entry["evidence_type"] == "self_test_diff"
    assert "base_exit_code" not in entry
    assert "severity" not in entry
    assert policy._has_real_execution_evidence([entry]) is False


def test_the_court_gate_still_refuses_counted_but_unrecorded_evidence() -> None:
    """A REGRESSION with no recorded exits must not satisfy the BLOCKER floor."""
    entry = {"evidence_type": "base_pass_head_fail", "verdict": "REGRESSION"}
    assert policy._has_real_execution_evidence([entry]) is False
    entry = {"evidence_type": "base_pass_head_fail", "verdict": "REGRESSION",
             "base_exit_code": 0, "head_exit_code": 1}
    assert policy._has_real_execution_evidence([entry]) is True
