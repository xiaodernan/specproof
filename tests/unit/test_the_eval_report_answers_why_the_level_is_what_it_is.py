"""The eval report must answer WHY a case got the level it got — from the page.

The severity of a finding is decided by the EVIDENCE behind it, so a reader
who sees "MAJOR where BLOCKER was expected" is holding a QUESTION. The
answer lives in two places the record carried but the page did not show:

* the differential's own verdict (`REGRESSION` / `AMBIGUOUS` / …) with the
  two sides' exit codes — that is what says whether anything RAN;
* whether the generated counterexample test could testify at all. A test
  that never compiled cannot testify about anything, and "both sides
  failed" without that fact is not a diagnosis, it is a shrug (#1636).

The page is the artifact a human reads (the JSON sidecar is a second
artifact nobody opens), so the answer belongs on the page.
"""

from __future__ import annotations

from typing import Any

from cli.specproof.commands.eval import _generation_evidence
from evidence.report import render_eval_report


def _record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case": "case-01",
        "verdict": "FALSE_POSITIVE",
        "should_detect": False,
        "expected_contract": "—",
        "expected_severity": "NONE",
        "expected_evidence": "none",
        "matched_findings": 0,
        "matched_severities": "—",
        "contracts_found": "AUTH-01",
        "severity_match": None,
        "finding_evidence": [],
    }
    record.update(overrides)
    return record


def _row_for(html: str, case: str) -> str:
    body = html.split("<tbody>")[1].split("</tr>")
    for row in body:
        if case in row:
            return row
    raise AssertionError(f"no row for {case}")


def test_the_record_says_whether_the_generated_test_compiled() -> None:
    """The generation record is the only witness for "it never compiled"."""
    final = {
        "generated_tests_path": "/tmp/SpecProofGeneratedTest.java",
        "generation_record": {
            "source": "llm_generated",
            "attempts": 2,
            "compile_passed": False,
            "errors": ["LLM generation failed: COMPILATION ERROR"],
            "head_run": {"exit_code": 1, "compile_error": True},
        },
    }
    evidence = _generation_evidence(final)
    assert evidence["generated"] is True
    assert evidence["compile_passed"] is False
    assert evidence["compile_error"] is True
    assert evidence["head_exit_code"] == 1
    assert "COMPILATION ERROR" in evidence["first_error"]


def test_a_run_without_a_generated_test_says_so() -> None:
    evidence = _generation_evidence({})
    assert evidence["generated"] is False
    assert evidence["compile_passed"] is False
    assert evidence["first_error"] == ""


def test_the_page_shows_the_differentials_own_words() -> None:
    html = render_eval_report(
        [
            _record(
                case="case-12",
                differential=[
                    {
                        "contract_id": "AUTH-01",
                        "verdict": "REGRESSION",
                        "detail": "Test passes in Base (exit 0) but fails in Head.",
                        "base_exit_code": 0,
                        "head_exit_code": 1,
                    }
                ],
            )
        ],
        None,
    )
    row = _row_for(html, "case-12")
    assert "REGRESSION" in row, row
    assert "0 → 1" in row, row


def test_the_page_says_when_the_generated_test_never_compiled() -> None:
    html = render_eval_report(
        [
            _record(
                case="case-13",
                generated_test={
                    "generated": True,
                    "source": "llm_generated",
                    "attempts": 2,
                    "compile_passed": False,
                    "compile_error": True,
                    "head_exit_code": 1,
                    "first_error": "COMPILATION ERROR",
                },
            )
        ],
        None,
    )
    row = _row_for(html, "case-13")
    assert "never compiled" in row, row


def test_a_record_from_an_older_run_still_renders() -> None:
    """The field used to be a bare bool; an old sidecar must still render."""
    html = render_eval_report(
        [_record(case="case-old", generated_test=True)], None
    )
    row = _row_for(html, "case-old")
    assert "generated" in row, row


def test_the_page_shows_the_failing_assertion() -> None:
    """"base passed, head failed" is the SHAPE of a regression; the failing
    assertion is the DIAGNOSIS. On a negative case it is often the generated
    test's own expectation being wrong -- and the reader must be able to see
    that without re-running the pipeline."""
    html = render_eval_report(
        [
            _record(
                case="case-52",
                differential=[
                    {
                        "contract_id": "AUTH-01",
                        "verdict": "REGRESSION",
                        "detail": "Test passes in Base (exit 0) but fails in Head.",
                        "base_exit_code": 0,
                        "head_exit_code": 1,
                        "head_failure": (
                            "type=org.opentest4j.AssertionFailedError | "
                            "message=expected 200 but was 404"
                        ),
                    }
                ],
            )
        ],
        None,
    )
    row = _row_for(html, "case-52")
    assert "expected 200 but was 404" in row, row


def test_a_case_that_ran_nothing_says_not_run() -> None:
    html = render_eval_report([_record(case="case-none")], None)
    row = _row_for(html, "case-none")
    assert "not run" in row, row
    assert "none" in row, row
