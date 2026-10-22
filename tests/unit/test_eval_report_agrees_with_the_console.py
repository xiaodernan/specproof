"""The HTML report and the console must not disagree about the same run.

Ledger #414 found THREE disagreements between the two artifacts, all of
them measured, not guessed:

1. **The report published an impossible recall.** It counted NEGATIVE
   cases (whose verdict is PASS) as detections, so the real 56-record run
   showed "Recall 169.7%" and "F1 125.8%" on the page while the console
   said 100.0%. The report also put never-measured cases in the recall
   DENOMINATOR while its own "Not Measured" stat said they were out of
   it. The counting rule is now the run's rule (``counter_deltas``), used
   by both.

2. **The retry story was only in the console.** A reader of the artifact
   could not tell a wobbling detection from a case that was never
   measured.

3. **A case that was missed EVERY time was called "unstable
   detection".** There was no detection to wobble. The retry reason is
   now classified by ONE rule with FOUR outcomes.

These tests are SHARP: reverting any of the fixes makes them fail.
"""

from __future__ import annotations

import json
import re
from typing import Any

from evidence.acceptance import (
    RETRY_CONSISTENTLY_MISSED,
    RETRY_FIRST_ATTEMPT_UNJUDGED,
    RETRY_NEVER_MEASURED,
    RETRY_UNSTABLE_DETECTION,
    count_records,
    retry_reason,
    retry_summary,
)
from evidence.report import render_eval_report


def _record(
    case: str,
    *,
    verdict: str = "PASS",
    should_detect: bool = True,
    attempts: int = 1,
    first_attempt_verdict: str | None = None,
) -> dict[str, Any]:
    detected = verdict in ("PASS", "PARTIAL")
    record: dict[str, Any] = {
        "case": case,
        "verdict": verdict,
        "should_detect": should_detect,
        "duration_ms": 1000,
        "attempts": attempts,
        "first_attempt_verdict": (
            first_attempt_verdict if first_attempt_verdict is not None else verdict
        ),
        "expected_contract": "COURT-01",
        "expected_severity": "MAJOR",
        "expected_evidence": "base_pass_head_fail",
        "matched_findings": 1 if detected else 0,
        "matched_severities": "MAJOR" if detected else "",
        "contract_level": "MAJOR" if detected else "",
        "all_matched_severities": "MAJOR" if detected else "",
        "contracts_found": "COURT-01" if detected else "",
        "finding_evidence": (
            [
                {
                    "contract_id": "COURT-01",
                    "severity": "MAJOR",
                    "evidence_type": "base_pass_head_fail",
                }
            ]
            if detected
            else []
        ),
    }
    return record


def _stat(html: str, label: str) -> str:
    """The value of the stat box with this label."""
    match = re.search(
        r'<div class="value"[^>]*>([^<]*)</div>\s*<div class="label">'
        + re.escape(label)
        + r"</div>",
        html,
    )
    assert match is not None, f"no stat box labelled {label!r}"
    return match.group(1)


# -- 1. the report's numbers are the run's numbers --------------------------


def test_a_negative_case_is_not_a_detection_in_the_report() -> None:
    """A negative case's verdict is PASS - it is NOT a detection.

    Sharp: with the report's own inline counting this case was counted
    as a detection and the recall came out ABOVE 100%.
    """
    records = [
        _record("case-01"),
        _record("case-02"),
        _record("case-03", verdict="MISS"),
        _record("case-04", should_detect=False),
    ]
    html = render_eval_report(records, None)
    assert _stat(html, "Recall") == "66.7%", html[:2000]
    assert _stat(html, "Detected / Should Detect") == "2/3"


def test_a_never_measured_case_is_out_of_the_recall_denominator() -> None:
    """The report's own "Not Measured" stat and its recall must agree.

    Sharp: with the inline counting the never-measured case was in the
    denominator, so the page said "out of the denominator" (in the stat)
    and put it in (in the ratio).
    """
    records = [
        _record("case-01"),
        _record("case-02"),
        _record("case-03", verdict="NOT_RUN"),
    ]
    html = render_eval_report(records, None)
    assert _stat(html, "Not Measured") == "1"
    assert _stat(html, "Recall") == "100.0%", html[:2000]
    # The never-measured case is in NEITHER side: 2 detected out of 2 that
    # were compared (not 2 out of 3).
    assert _stat(html, "Detected / Should Detect") == "2/2"


def test_the_report_and_the_counting_rule_agree() -> None:
    """The report's numbers come from the run's counting rule."""
    records = [
        _record("case-01"),
        _record("case-02", verdict="MISS"),
        _record("case-03", should_detect=False),
        _record("case-04", should_detect=False, verdict="FALSE_POSITIVE"),
    ]
    counts, not_measured = count_records(records)
    html = render_eval_report(records, None)
    assert _stat(html, "Detected / Should Detect") == (
        f"{counts.detected}/{counts.should_detect}"
    )
    assert _stat(html, "Not Measured") == str(not_measured)
    assert _stat(html, "False Positives") == str(counts.false_positives)


def test_the_recall_on_the_page_can_never_exceed_a_hundred() -> None:
    """A recall above 100% is not a metric - it is a counting bug.

    This is the property the 169.7% broke.
    """
    records = [
        _record("case-01"),
        _record("case-02"),
        _record("case-03", should_detect=False),
        _record("case-04", should_detect=False),
    ]
    html = render_eval_report(records, None)
    recall = _stat(html, "Recall")
    assert recall.endswith("%")
    assert float(recall.rstrip("%")) <= 100.0, recall


# -- 2. the retry story is in the report too --------------------------------


def test_the_report_says_how_many_cases_were_measured_more_than_once() -> None:
    records = [
        _record("case-01"),
        _record("case-02", attempts=3, first_attempt_verdict="NOT_RUN"),
    ]
    html = render_eval_report(records, None)
    assert _stat(html, "Measured More Than Once") == "1"
    assert "Measured more than once (1)" in html
    assert "case-02" in html


def test_a_run_with_no_retries_says_zero() -> None:
    html = render_eval_report([_record("case-01")], None)
    assert _stat(html, "Measured More Than Once") == "0"
    assert "Measured more than once" not in html


# -- 3. four reasons, not three ---------------------------------------------


def test_a_case_missed_every_time_is_not_an_unstable_detection() -> None:
    """There was NO detection to wobble.

    Sharp: with the three-way rule this case was called "unstable
    detection" - the label claims the detection changed its mind about a
    run that never detected anything.
    """
    record = _record("case-01", verdict="MISS", attempts=3,
                      first_attempt_verdict="MISS")
    assert retry_reason(record) == RETRY_CONSISTENTLY_MISSED
    html = render_eval_report([record], None)
    assert "consistently missed" in html
    assert "unstable detection" not in html


def test_the_four_reasons_are_four_different_things() -> None:
    cases = {
        RETRY_NEVER_MEASURED: _record("a", verdict="NOT_RUN", attempts=3,
                                      first_attempt_verdict="NOT_RUN"),
        RETRY_FIRST_ATTEMPT_UNJUDGED: _record("b", verdict="MISS", attempts=3,
                                              first_attempt_verdict="NOT_RUN"),
        RETRY_CONSISTENTLY_MISSED: _record("c", verdict="MISS", attempts=3,
                                            first_attempt_verdict="MISS"),
        RETRY_UNSTABLE_DETECTION: _record("d", verdict="PASS", attempts=2,
                                          first_attempt_verdict="MISS"),
    }
    reasons = {retry_reason(rec) for rec in cases.values()}
    assert reasons == set(cases), reasons
    # and each reason is the one the rule says it is
    for expected, record in cases.items():
        assert retry_reason(record) == expected


def test_a_detection_that_really_wobbled_is_still_called_that() -> None:
    record = _record("case-01", verdict="PASS", attempts=2,
                      first_attempt_verdict="MISS")
    assert retry_reason(record) == RETRY_UNSTABLE_DETECTION
    html = render_eval_report([record], None)
    assert "unstable detection" in html


def test_the_summary_counts_each_reason_separately() -> None:
    records = [
        _record("a", verdict="NOT_RUN", attempts=3, first_attempt_verdict="NOT_RUN"),
        _record("b", verdict="MISS", attempts=3, first_attempt_verdict="NOT_RUN"),
        _record("c", verdict="MISS", attempts=3, first_attempt_verdict="MISS"),
        _record("d", verdict="PASS", attempts=2, first_attempt_verdict="MISS"),
        _record("e"),
    ]
    summary = retry_summary(records)
    assert summary["retried_cases"] == 4
    assert summary["by_reason"] == {
        RETRY_NEVER_MEASURED: 1,
        RETRY_FIRST_ATTEMPT_UNJUDGED: 1,
        RETRY_CONSISTENTLY_MISSED: 1,
        RETRY_UNSTABLE_DETECTION: 1,
    }
    assert [entry["case"] for entry in summary["retries"]] == ["a", "b", "c", "d"]


def test_the_page_says_how_many_negatives_the_precision_rests_on() -> None:
    """Precision is only challenged by the negative cases.

    "Precision 100%" over ZERO negatives is a number nobody can lean on -
    the acceptance gate has a ``min_negative_cases`` floor for exactly
    that reason, so the count has to be visible too.
    """
    records = [_record("case-01")]
    html = render_eval_report(records, None)
    assert _stat(html, "Negative Cases") == "0"

    records = [
        _record("case-01"),
        _record("case-02", should_detect=False),
        _record("case-03", should_detect=False, verdict="FALSE_POSITIVE"),
    ]
    html = render_eval_report(records, None)
    assert _stat(html, "Negative Cases") == "2"
    assert _stat(html, "False Positives") == "1"


# -- end to end: the real CLI, the real page --------------------------------


def _write_case(root, name: str, *, should_detect: bool):
    case_dir = root / name
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "spec.md").write_text(
        f"# {name}\n\nThe service must reject a null event timestamp.\n",
        encoding="utf-8",
    )
    (case_dir / "ground-truth.json").write_text(
        json.dumps({
            "should_detect": should_detect,
            "expected_contract": "COURT-01",
            "expected_severity": "MAJOR",
            "expected_min_findings": 1,
        }),
        encoding="utf-8",
    )
    (case_dir / "scenario.json").write_text(
        json.dumps({"base_ref": "base", "head_ref": "head-v1"}), encoding="utf-8"
    )
    return case_dir


class _Finds:
    """A positive case the tool detects."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: dict) -> dict:
        self.calls += 1
        return {
            "confirmed_findings": [{
                "id": "f-1",
                "contract_id": "COURT-01",
                "severity": "MAJOR",
                "confidence": 0.9,
                "evidence_type": "DIFFERENTIAL",
            }],
            "errors": [],
        }


class _FindsNothing:
    """A positive case the tool never detects."""

    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, state: dict) -> dict:
        self.calls += 1
        return {"confirmed_findings": [], "errors": []}


def test_the_page_the_run_wrote_says_what_the_run_said(tmp_path, monkeypatch) -> None:
    """The end-to-end property: run the CLI, then read the page it wrote.

    A positive case it detects, a positive case it misses, and a negative
    case it passes. The console prints four numbers; the page must print
    the same four.
    """
    from click.testing import CliRunner

    import agent.graph
    from cli.specproof.commands import eval as eval_module
    from cli.specproof.commands.eval import eval_cmd

    class _Graph:
        def __init__(self) -> None:
            self.n = 0

        def invoke(self, state: dict) -> dict:
            self.n += 1
            # the first case is detected, the second is not
            if self.n == 1:
                return _Finds().invoke(state)
            return _FindsNothing().invoke(state)

    monkeypatch.setattr(agent.graph, "build_phase0_graph", lambda: _Graph())
    monkeypatch.setattr(eval_module, "_schema_reachable", lambda _db: False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)

    (tmp_path / "cases").mkdir()
    (tmp_path / "repo").mkdir()
    _write_case(tmp_path / "cases", "case-01-detected", should_detect=True)
    _write_case(tmp_path / "cases", "case-02-missed", should_detect=True)
    _write_case(tmp_path / "cases", "case-03-negative", should_detect=False)

    result = CliRunner().invoke(
        eval_cmd,
        [
            "--cases", str(tmp_path / "cases"),
            "--repo", str(tmp_path / "repo"),
            "--no-llm", "--include-holdout",
            "--attempts", "1",
            "--output", str(tmp_path / "eval-report.html"),
        ],
    )
    assert result.exit_code == 0, result.output

    console = result.output
    should = re.search(r"Should detect:\s+(\d+)", console).group(1)
    detected = re.search(r"Detected:\s+(\d+)", console).group(1)
    negatives = re.search(r"Negative cases:\s+(\d+)", console).group(1)
    not_run = re.search(r"Not run:\s+(\d+)", console).group(1)

    html = (tmp_path / "eval-report.html").read_text(encoding="utf-8")
    assert _stat(html, "Detected / Should Detect") == f"{detected}/{should}"
    assert _stat(html, "False Positives") == "0"
    assert _stat(html, "Not Measured") == not_run
    # The count of negatives is what makes the precision meaningful, so it
    # is on the page next to it (ledger #415).
    assert _stat(html, "Negative Cases") == negatives
    assert _stat(html, "Recall") != "", "the page has a recall"


def test_the_page_and_the_console_agree_on_the_case_that_was_retried(
    tmp_path, monkeypatch
) -> None:
    """A case that needed a second attempt appears in the page's retry list
    with the same reason the console gave it."""
    from click.testing import CliRunner

    import agent.graph
    from cli.specproof.commands import eval as eval_module
    from cli.specproof.commands.eval import eval_cmd

    class _Flaky:
        def __init__(self) -> None:
            self.n = 0

        def invoke(self, state: dict) -> dict:
            self.n += 1
            if self.n == 1:
                return {"confirmed_findings": [], "errors": []}
            return _Finds().invoke(state)

    monkeypatch.setattr(agent.graph, "build_phase0_graph", lambda: _Flaky())
    monkeypatch.setattr(eval_module, "_schema_reachable", lambda _db: False)
    monkeypatch.delenv("MYSQL_DATABASE", raising=False)
    monkeypatch.delenv("SPECPROOF_TEST_MYSQL_DATABASE", raising=False)

    (tmp_path / "cases").mkdir()
    (tmp_path / "repo").mkdir()
    _write_case(tmp_path / "cases", "case-01-flaky", should_detect=True)

    result = CliRunner().invoke(
        eval_cmd,
        [
            "--cases", str(tmp_path / "cases"),
            "--repo", str(tmp_path / "repo"),
            "--no-llm", "--include-holdout",
            "--attempts", "3",
            "--output", str(tmp_path / "eval-report.html"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "! unstable detection: case-01-flaky" in result.output, result.output

    html = (tmp_path / "eval-report.html").read_text(encoding="utf-8")
    assert _stat(html, "Measured More Than Once") == "1"
    assert "unstable detection" in html
    assert "case-01-flaky" in html
