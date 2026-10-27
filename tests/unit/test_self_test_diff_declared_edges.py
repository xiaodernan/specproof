"""#453 — the self-test verdict's summary-parsing corners.

``agent/self_test_diff.py`` turns parsed test-count dicts into a differential
verdict. ``test_self_test_diff.py`` already pins the four verdicts, the
surefire/pytest/node reporter shapes, the all-skipped arms and the
default-off host-execution gate.

What it does not reach:

* the ``_side`` **derivation** branch — a summary with no ``tests`` key
  at all, where the count has to be derived from the individual parts;
* a summary with no ``tests`` key and no usable parts either;
* the ``NO_EVIDENCE`` detail string naming **both** sides, and naming
  **base only** (only the "head" wording is pinned today);
* the clamp in ``_executed``: ``skipped`` exceeding ``tests`` with no
  ``passed`` key drives the executed count to zero, which is honest;
* the "(N tests)" figure in the detail string, which since #456 reports the
  number of tests that actually ran rather than the reporter's ``tests``
  key. #479 adds the one summary that tells those two numbers apart while
  both are still positive: until then every case here either had ``tests``
  absent or ``tests`` already equal to the ran count, so a reader that went
  back to the reporter's key would have kept this file green — which is
  also how #456's second, Optional-typed derivation of the same number
  stayed invisible to the suite while CI's ``mypy .`` step charged it.
"""
from __future__ import annotations

from agent.self_test_diff import (
    VERDICT_NO_EVIDENCE,
    VERDICT_REGRESSION,
    self_test_verdict,
)

GREEN = {"tests": 5, "passed": 5, "failed": 0, "errors": 0, "skipped": 0}


# ── A summary with no "tests" key ──────────────────────────────────────


def test_a_summary_without_a_tests_key_still_derives_its_count() -> None:
    # No "tests" key: the executed/failing figures must be derived from the
    # individual parts rather than read as zero.
    base = {"passed": 3, "failed": 0, "errors": 0, "skipped": 0}
    head = {"passed": 3, "failed": 1, "errors": 0, "skipped": 0}
    verdict, detail = self_test_verdict(base, head)
    assert verdict == VERDICT_REGRESSION
    assert "1 fail" in detail


def test_a_summary_with_no_tests_key_and_no_counts_is_no_evidence() -> None:
    # Nothing to derive from either: an honest no-evidence, not a pass.
    verdict, detail = self_test_verdict({"skipped": 0}, dict(GREEN))
    assert verdict == VERDICT_NO_EVIDENCE
    assert "base" in detail


# ── The NO_EVIDENCE wording ────────────────────────────────────────────


def test_no_evidence_detail_names_both_sides() -> None:
    verdict, detail = self_test_verdict(None, None)
    assert verdict == VERDICT_NO_EVIDENCE
    assert "base and head" in detail


def test_no_evidence_detail_names_base_only() -> None:
    green = dict(GREEN)
    verdict, detail = self_test_verdict({"tests": 0, "passed": 0, "failed": 0}, green)
    assert verdict == VERDICT_NO_EVIDENCE
    assert "for base" in detail
    assert "head" not in detail


# ── The clamp ──────────────────────────────────────────────────────────


def test_skipped_exceeding_tests_without_a_passed_key_is_no_evidence() -> None:
    # No "passed" key, so the executed count is derived as tests - skipped and
    # clamped at zero: nothing actually ran, so there is no evidence.
    head = {"tests": 3, "failures": 1, "errors": 0, "skipped": 7}
    verdict, detail = self_test_verdict(dict(GREEN), head)
    assert verdict == VERDICT_NO_EVIDENCE
    assert "head" in detail


# ── The count in the message ───────────────────────────────────────────


def test_the_detail_reports_the_count_of_tests_that_ran() -> None:
    # The verdict is correct (REGRESSION) and, since #456, the "(N tests)"
    # figure reports the number of tests that actually ran rather than the
    # reporter's "tests" key — so a reporter that publishes only passed/failed
    # is described as "(3 tests)", not "(0 tests)".
    base = {"passed": 3, "failed": 0, "errors": 0, "skipped": 0}
    head = {"passed": 3, "failed": 1, "errors": 0, "skipped": 0}
    verdict, detail = self_test_verdict(base, head)
    assert verdict == VERDICT_REGRESSION
    assert "(3 tests)" in detail


def test_a_normal_reporter_still_reports_its_own_test_count() -> None:
    # The fix must not disturb the ordinary case: a reporter that publishes
    # "tests" and "passed" reports exactly that count.
    base = {"tests": 10, "passed": 10, "failed": 0, "errors": 0, "skipped": 0}
    head = {"tests": 10, "passed": 8, "failed": 2, "errors": 0, "skipped": 0}
    verdict, detail = self_test_verdict(base, head)
    assert verdict == VERDICT_REGRESSION
    assert "(10 tests)" in detail


def test_the_figure_is_the_ran_count_when_the_reporter_publishes_a_bigger_tests_key() -> None:
    # Surefire folds the skipped ones into "tests": 9 there, 3 of which ran. Both
    # numbers are positive, so this is the summary that separates "how many ran"
    # from "how many the reporter counted" — the legs above only ever had one of
    # the two available.
    base = {"tests": 9, "passed": 3, "failed": 0, "errors": 0, "skipped": 6}
    head = {"tests": 9, "passed": 2, "failed": 1, "errors": 0, "skipped": 6}
    verdict, detail = self_test_verdict(base, head)
    assert verdict == VERDICT_REGRESSION
    assert "(3 tests)" in detail, detail
    assert "(9 tests)" not in detail, detail
