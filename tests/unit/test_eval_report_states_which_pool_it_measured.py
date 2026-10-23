"""The page must say WHICH POOL its numbers came from.

The console has always said it out loud:

    ! 本轮未做 holdout 隔离（--include-holdout）：这些数字不是未见过案例上的指标。

The HTML report said nothing about it. So a reader of the page - the
artifact CI uploads, the artifact a human opens - could take
"Recall 100.0%" for a metric on UNSEEN cases while the run had merged
the holdout pool in. The run that produced the current numbers is
exactly such a run (``--include-holdout``).

The pool is recorded in the sidecar (``case_set``), so the page can
state it (ledger #423).

These tests are SHARP: dropping the case set from the page makes them
fail.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evidence.report import render_eval_report
from scripts.render_eval_report import load_evidence


def _record(case: str = "case-01") -> dict[str, Any]:
    return {
        "case": case,
        "verdict": "PASS",
        "should_detect": True,
        "expected_contract": "COURT-01",
        "expected_severity": "MAJOR",
        "expected_evidence": "base_pass_head_fail",
        "matched_findings": 1,
        "matched_severities": "MAJOR",
        "contract_level": "MAJOR",
        "all_matched_severities": "MAJOR",
        "contracts_found": "COURT-01",
        "finding_evidence": [],
    }


def _case_set(**overrides: Any) -> dict[str, Any]:
    case_set: dict[str, Any] = {
        "mode": "tuning",
        "manifest_path": "docs/eval/holdout-manifest.json",
        "excluded_holdout_cases": ["case-101"],
        "declared_but_absent": ["case-102"],
        "manifest_note": "a note",
    }
    case_set.update(overrides)
    return case_set


def test_a_run_without_holdout_isolation_says_so_on_the_page() -> None:
    """The caveat that decides what the numbers MEAN.

    Sharp: without this the page shows "Recall 100.0%" next to nothing
    that says the pool included the cases that were held out.
    """
    html = render_eval_report(
        [_record()], None, _case_set(mode="all_not_isolated")
    )
    assert "holdout" in html
    assert "未见过案例" in html, html[:3000]


def test_the_excluded_cases_are_named() -> None:
    html = render_eval_report([_record()], None, _case_set())
    assert "case-101" in html
    assert "case-102" in html
    assert "manifest note" in html


def test_a_run_with_isolation_states_the_mode() -> None:
    html = render_eval_report([_record()], None, _case_set(mode="tuning"))
    assert "tuning" in html
    assert "未见过案例" not in html


def test_a_page_without_a_case_set_says_nothing_about_one() -> None:
    """A report rendered from records alone has no pool to report."""
    html = render_eval_report([_record()], None)
    assert "holdout" not in html


def test_the_sidecar_carries_the_pool_and_the_re_render_reads_it(
    tmp_path: Path,
) -> None:
    """The re-rendered page must state the pool too.

    A page re-rendered from the sidecar is the page a reader gets; if
    the pool was dropped on the way, the caveat disappears with it.
    """
    sidecar = tmp_path / "eval-report.results.json"
    sidecar.write_text(
        json.dumps({"cases": [_record()], "case_set": _case_set(
            mode="all_not_isolated"
        )}),
        encoding="utf-8",
    )
    cases, acceptance, case_set = load_evidence(sidecar)
    assert acceptance is None
    assert case_set is not None
    assert case_set["mode"] == "all_not_isolated"

    html = render_eval_report(cases, acceptance, case_set)
    assert "未见过案例" in html


def test_an_incremental_sidecar_carries_no_pool() -> None:
    """The pool is written at the END of a run.

    A killed run has no pool to report, and none is invented.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        sidecar = Path(tmp) / "eval-report.results.jsonl"
        sidecar.write_text(json.dumps(_record()) + "\n", encoding="utf-8")
        cases, acceptance, case_set = load_evidence(sidecar)
    assert len(cases) == 1
    assert acceptance is None
    assert case_set is None


def test_the_eval_command_hands_the_pool_to_the_report() -> None:
    """The pool the run measured is the pool the page must state."""
    eval_py = (
        Path(__file__).resolve().parents[2]
        / "cli" / "specproof" / "commands" / "eval.py"
    ).read_text(encoding="utf-8")
    assert "render_eval_report(results, acceptance, plan.as_json())" in eval_py, (
        "the eval command must hand the plan to the report - otherwise the "
        "page cannot state which pool the numbers came from"
    )
