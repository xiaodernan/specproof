"""Unit tests for the roadmap 4a self-test differential groundwork.

These lock the pure verdict math + the default-off execution gate. They use
FAKE parsed-count dicts only — nothing here runs an adapter, a build, or a
subprocess, which is exactly the point: the execution wiring is deliberately
absent until a Node/Python sandbox exists.
"""
from __future__ import annotations

import pytest

from agent.self_test_diff import (
    ALLOW_LOCAL_TEST_EXEC_ENV,
    VERDICT_AMBIGUOUS,
    VERDICT_COMPLIANT,
    VERDICT_NO_EVIDENCE,
    VERDICT_REGRESSION,
    VERDICT_UNEXPECTED_FIX,
    self_test_execution_allowed,
    self_test_verdict,
)


def test_base_green_head_broken_is_regression() -> None:
    base = {"tests": 10, "passed": 10, "failed": 0, "errors": 0, "skipped": 0}
    head = {"tests": 10, "passed": 8, "failed": 2, "errors": 0, "skipped": 0}
    verdict, detail = self_test_verdict(base, head)
    assert verdict == VERDICT_REGRESSION
    assert "2 fail" in detail


def test_both_green_is_compliant() -> None:
    green = {"tests": 5, "passed": 5, "failed": 0, "errors": 0, "skipped": 0}
    verdict, _ = self_test_verdict(green, dict(green))
    assert verdict == VERDICT_COMPLIANT


def test_base_broken_head_green_is_unexpected_fix() -> None:
    base = {"tests": 4, "passed": 3, "failed": 1, "errors": 0, "skipped": 0}
    head = {"tests": 4, "passed": 4, "failed": 0, "errors": 0, "skipped": 0}
    verdict, _ = self_test_verdict(base, head)
    assert verdict == VERDICT_UNEXPECTED_FIX


def test_both_broken_is_ambiguous() -> None:
    base = {"tests": 4, "passed": 2, "failed": 2, "errors": 0, "skipped": 0}
    head = {"tests": 4, "passed": 1, "failed": 3, "errors": 0, "skipped": 0}
    verdict, _ = self_test_verdict(base, head)
    assert verdict == VERDICT_AMBIGUOUS


def test_surefire_failures_key_is_recognized() -> None:
    # parse_surefire_summary uses "failures", not "failed".
    base = {"tests": 3, "failures": 0, "errors": 0, "skipped": 0}
    head = {"tests": 3, "failures": 1, "errors": 0, "skipped": 0}
    verdict, _ = self_test_verdict(base, head)
    assert verdict == VERDICT_REGRESSION


def test_error_count_counts_as_failing() -> None:
    base = {"tests": 3, "passed": 3, "failed": 0, "errors": 0}
    head = {"tests": 3, "passed": 2, "failed": 0, "errors": 1}
    verdict, _ = self_test_verdict(base, head)
    assert verdict == VERDICT_REGRESSION


@pytest.mark.parametrize("empty", [None, {}, {"tests": 0, "passed": 0, "failed": 0}])
def test_no_counts_is_no_evidence_never_a_pass(empty: dict[str, int] | None) -> None:
    green = {"tests": 5, "passed": 5, "failed": 0, "errors": 0, "skipped": 0}
    # A zero-test / absent summary must not be laundered into COMPLIANT.
    verdict, detail = self_test_verdict(green, empty)
    assert verdict == VERDICT_NO_EVIDENCE
    assert "head" in detail
    verdict2, _ = self_test_verdict(empty, green)
    assert verdict2 == VERDICT_NO_EVIDENCE


    verdict2, _ = self_test_verdict(empty, green)
    assert verdict2 == VERDICT_NO_EVIDENCE


# ---- all-skipped runs are not green runs (#237) -------------------------------
#
# The five reporters disagree about what "tests" counts, and the disagreement
# is load-bearing. surefire / Jest / Vitest / node:test fold skipped tests INTO
# "tests"; pytest's "tests" is passed+failed and already excludes them. So
# neither extreme is right: subtracting "skipped" unconditionally drives
# pytest negative, and never subtracting it certifies an all-skipped suite as
# COMPLIANT -- which is what these four lock shut.

GREEN = {"tests": 5, "passed": 5, "failed": 0, "errors": 0, "skipped": 0}


def test_all_skipped_surefire_is_not_compliant() -> None:
    # parse_surefire_summary shape: "tests" includes the skipped ones.
    skipped = {"tests": 3, "failures": 0, "errors": 0, "skipped": 3}
    verdict, detail = self_test_verdict(dict(GREEN), skipped)
    assert verdict == VERDICT_NO_EVIDENCE
    assert "head" in detail


def test_all_skipped_node_reporter_is_not_compliant() -> None:
    # parse_node_test_summary shape: "tests" includes skipped/pending.
    skipped = {"tests": 4, "passed": 0, "failed": 0, "skipped": 4}
    verdict, _ = self_test_verdict(dict(GREEN), skipped)
    assert verdict == VERDICT_NO_EVIDENCE


def test_both_sides_all_skipped_is_not_compliant() -> None:
    skipped = {"tests": 4, "passed": 0, "failed": 0, "skipped": 4}
    verdict, _ = self_test_verdict(dict(skipped), dict(skipped))
    assert verdict == VERDICT_NO_EVIDENCE


def test_a_partial_skip_still_counts_the_tests_that_ran() -> None:
    # 2 ran and passed, 1 skipped: a green head. This is the arm that stops
    # the fix from over-correcting into "any skip means no evidence".
    head = {"tests": 3, "passed": 2, "failed": 0, "errors": 0, "skipped": 1}
    verdict, _ = self_test_verdict(dict(GREEN), head)
    assert verdict == VERDICT_COMPLIANT


def test_pytest_summary_is_not_double_subtracted() -> None:
    # pytest's "tests" already excludes skipped (5 = 4 passed + 1 failed), so
    # "tests - skipped" must never go negative and lose the failing test.
    head = {"tests": 5, "passed": 4, "failed": 1, "errors": 0, "skipped": 7}
    verdict, detail = self_test_verdict(dict(GREEN), head)
    assert verdict == VERDICT_REGRESSION
    assert "1 fail" in detail

def test_verdict_is_reproducible_across_equal_inputs() -> None:
    base = {"tests": 10, "passed": 10, "failed": 0, "errors": 0, "skipped": 0}
    head = {"tests": 10, "passed": 9, "failed": 1, "errors": 0, "skipped": 0}
    assert self_test_verdict(base, head) == self_test_verdict(base, head)


def test_gate_is_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ALLOW_LOCAL_TEST_EXEC_ENV, raising=False)
    assert self_test_execution_allowed() is False


@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "Yes", "on", "  1  "])
def test_gate_on_only_for_explicit_truthy(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv(ALLOW_LOCAL_TEST_EXEC_ENV, raw)
    assert self_test_execution_allowed() is True


@pytest.mark.parametrize("raw", ["0", "false", "", "maybe", "off", "2"])
def test_gate_stays_off_for_anything_else(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    monkeypatch.setenv(ALLOW_LOCAL_TEST_EXEC_ENV, raw)
    assert self_test_execution_allowed() is False
