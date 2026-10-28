"""An unreadable JUnit report must not be reported as "0 tests ran".

`GradleAdapter._parse_test_results` returns the XML counts as soon as any
`*.xml` exists under `build/test-results/test`, and `_parse_junit_xml` skips a
report it cannot parse. Together that meant: a corrupt/unreadable report was
reported as `(0, 0, 0, 0)` — "this run had no tests" — and the console-summary
fallback was skipped entirely, because the function had already returned.

That is the shape this repo keeps calling out ("跳过 ≠ 通过"), and it was
introduced by a justification, not by a design: #508 wrote "an unreadable report
is skipped, never counted as zero tests" next to the handler, and #509 found the
code did exactly the opposite. The comment is only worth something if a test
holds the behaviour to it.

The go leg is the mirror image: its blind catch wrapped `re.findall` /
`re.search` with literal patterns, which cannot raise, so the catch was dead
code and its justification described a fallback mechanism that did not exist
(the fallback is `if tests_run == 0`). It is gone; these legs keep the parsing
that used to sit inside it working.
"""

from __future__ import annotations

from pathlib import Path

from craft.adapters.go_adapter import GoAdapter
from craft.adapters.gradle_adapter import GradleAdapter


def _xml(project_root: Path, body: str, name: str = "TEST-demo.xml") -> Path:
    reports = project_root / "build" / "test-results" / "test"
    reports.mkdir(parents=True, exist_ok=True)
    path = reports / name
    path.write_text(body, encoding="utf-8")
    return path


def test_an_unreadable_report_falls_back_to_the_console_summary(tmp_path: Path) -> None:
    _xml(tmp_path, "<<< this is not xml >>>")

    counts = GradleAdapter._parse_test_results(
        tmp_path, "5 tests completed, 1 failed, 0 skipped", ""
    )

    assert counts == (5, 4, 1, 0), (
        "a report that could not be parsed must not be reported as zero tests; "
        f"got {counts}"
    )


def test_a_readable_report_still_wins_over_the_console(tmp_path: Path) -> None:
    _xml(
        tmp_path,
        '<testsuite name="d.T" tests="7" failures="2" errors="0" skipped="1"/>',
    )

    counts = GradleAdapter._parse_test_results(
        tmp_path, "99 tests completed, 0 failed, 0 skipped", ""
    )

    assert counts == (7, 4, 2, 1), f"the XML is authoritative when it parses; got {counts}"


def test_no_report_at_all_uses_the_console(tmp_path: Path) -> None:
    counts = GradleAdapter._parse_test_results(
        tmp_path, "3 tests completed, 0 failed, 1 skipped", ""
    )

    assert counts == (3, 2, 0, 1)


def test_a_report_that_really_has_no_tests_is_not_a_parse_failure(tmp_path: Path) -> None:
    """An empty-but-valid report and a corrupt one both end up as zeros here.

    The distinction that matters is downstream: the exit code is the verdict,
    and `test_counts_source` records which channel the counts came from. This
    leg only pins that a valid zero-test report does not crash the parser.
    """
    _xml(tmp_path, '<testsuite name="d.T" tests="0" failures="0" errors="0" skipped="0"/>')

    assert GradleAdapter._parse_test_results(tmp_path, "", "") == (0, 0, 0, 0)


def test_the_go_parser_still_reads_the_keyword_summary() -> None:
    """The dead catch is gone; the parsing it wrapped must be unchanged."""
    output = "\n".join([
        "--- PASS: TestAdd (0.00s)",
        "--- PASS: TestSub (0.00s)",
        "--- FAIL: TestDiv (0.01s)",
        "--- SKIP: TestSlow (0.00s)",
    ])

    run, passed, failed, skipped = GoAdapter._parse_test_results(Path("."), output, "")

    assert (run, passed, failed, skipped) == (4, 2, 1, 1)


def test_the_go_parser_still_reads_the_json_event_counts() -> None:
    output = '{"Action":"pass"}\n{"status":"passed"}\n{"status":"failed"}'

    run, passed, failed, _skipped = GoAdapter._parse_test_results(Path("."), output, "")

    assert passed == 1 and failed == 1, f"json-style counts regressed: {(run, passed, failed)}"
