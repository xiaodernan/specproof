"""A case that was never measured must show BOTH sides' output.

The eval captures the output tail of each side that the evidence path
could not judge (``unjudgeable_output_tails`` returns ``base_output``
AND ``head_output``), the record carries both, and the console prints
both:

    base output: ...
    head output: ...

The HTML report rendered only the BASE's. So a case whose **head** side
was the one that failed showed the reason and **no output at all** -
which is exactly the diagnosis the output is there for (ledger #399 said
it: "the side that failed, and its own output: without them, 'the
evidence could not judge this case' is a symptom with no diagnosis
attached"). #417 closes the half that was left open.

This test is SHARP: reverting the report to the base-only rendering
makes it fail.
"""

from __future__ import annotations

from typing import Any

from evidence.report import render_eval_report


def _not_measured_record(**overrides: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "case": "case-01",
        "verdict": "NOT_RUN",
        "should_detect": True,
        "expected_contract": "COURT-01",
        "expected_severity": "MAJOR",
        "expected_evidence": "base_pass_head_fail",
        "matched_findings": 0,
        "matched_severities": "—",
        "contracts_found": "",
        "errors": "the evidence path could not judge this case",
        "finding_evidence": [],
        "base_output": "BASE-SIDE-OUTPUT-LINE",
        "head_output": "HEAD-SIDE-OUTPUT-LINE",
    }
    record.update(overrides)
    return record


def test_the_report_shows_the_base_output() -> None:
    html = render_eval_report([_not_measured_record()], None)
    assert "BASE-SIDE-OUTPUT-LINE" in html
    assert "base output" in html


def test_the_report_shows_the_head_output_too() -> None:
    """The head side is the one that often fails.

    Sharp: with the base-only rendering this string was not on the page
    at all, so a case whose head side failed had no diagnosis.
    """
    html = render_eval_report([_not_measured_record()], None)
    assert "HEAD-SIDE-OUTPUT-LINE" in html, html[-3000:]
    assert "head output" in html


def test_a_case_with_no_output_still_shows_its_reason() -> None:
    html = render_eval_report(
        [_not_measured_record(base_output="", head_output="")], None
    )
    assert "the evidence path could not judge this case" in html


def test_the_output_is_labelled_so_the_reader_knows_which_side_failed() -> None:
    html = render_eval_report([_not_measured_record()], None)
    # The two labels are distinct, and each sits with its own output.
    base_at = html.find("BASE-SIDE-OUTPUT-LINE")
    head_at = html.find("HEAD-SIDE-OUTPUT-LINE")
    assert base_at != -1 and head_at != -1
    assert "base output" in html[:base_at]
    assert "head output" in html[:head_at]
