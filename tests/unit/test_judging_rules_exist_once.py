"""The judging rules exist ONCE - and a finding without an id is a finding.

Two commands judge a case's findings: ``specproof eval`` (the tool's own
measurements) and ``specproof baseline`` (a baseline model's, so the two
can be compared). The baseline's docstring claimed it applies "the SAME
judging rules as specproof eval" and then wrote its own copy.

The copies had drifted, measured on the SAME findings (ledger #419):

- a finding **without an id**: the eval dropped every id-less finding
  after the first (they all share the key ``""``), so two real findings
  counted as one and a ``min_findings: 2`` expectation was not met;
- a finding reported **twice under one id**: the eval counted it once
  (right - it is one finding), the baseline counted it twice.

Both now read the ONE rule in ``evidence.judging``.

These tests are SHARP: putting the old copies back makes them fail.
"""

from __future__ import annotations

from typing import Any

from cli.specproof.commands.baseline import judge_case
from cli.specproof.commands.eval import matched_findings, verdict_for
from evidence.judging import matched_findings as shared_matched
from evidence.judging import verdict_for as shared_verdict

GT: dict[str, Any] = {
    "should_detect": True,
    "expected_contract": "COURT-01",
    "expected_evidence_type": "base_pass_head_fail",
    "expected_min_findings": 2,
}


def _finding(
    *,
    finding_id: str | None = "f-1",
    contract_id: str = "COURT-01",
    severity: str = "MAJOR",
    evidence_type: str = "base_pass_head_fail",
) -> dict[str, Any]:
    finding: dict[str, Any] = {
        "contract_id": contract_id,
        "severity": severity,
        "evidence_type": evidence_type,
    }
    if finding_id is not None:
        finding["id"] = finding_id
    return finding


def _eval_verdict(findings: list[dict[str, Any]]) -> str:
    matched = matched_findings(findings, "COURT-01", "base_pass_head_fail")
    return verdict_for(True, findings, matched, 2)


def _baseline_verdict(findings: list[dict[str, Any]]) -> str:
    return str(judge_case("case-01", GT, findings)["verdict"])


# -- one implementation -----------------------------------------------------


def test_the_eval_uses_the_shared_rule() -> None:
    findings = [_finding(), _finding(finding_id="f-2")]
    assert matched_findings(findings, "COURT-01", "base_pass_head_fail") == (
        shared_matched(findings, "COURT-01", "base_pass_head_fail")
    )


def test_a_finding_without_an_id_is_still_a_finding() -> None:
    """Two real findings, neither carrying an id: that is TWO findings.

    Sharp: the old rule keyed the de-duplication on ``f.get("id", "")``,
    so every id-less finding after the first shared the key ``""`` and
    was dropped - two findings counted as one, and a
    ``min_findings: 2`` expectation was not met.
    """
    findings = [
        _finding(finding_id=None, severity="MAJOR"),
        _finding(finding_id=None, severity="MINOR"),
    ]
    matched = matched_findings(findings, "COURT-01", "base_pass_head_fail")
    assert len(matched) == 2, matched
    assert verdict_for(True, findings, matched, 2) == "PASS"


def test_a_finding_reported_twice_under_one_id_is_one_finding() -> None:
    """The other half: a finding with an id IS recognised as a repeat.

    Counting it twice would let one finding satisfy a
    ``min_findings: 2`` expectation on its own.
    """
    findings = [_finding(finding_id="f-1"), _finding(finding_id="f-1")]
    matched = matched_findings(findings, "COURT-01", "base_pass_head_fail")
    assert len(matched) == 1
    assert verdict_for(True, findings, matched, 2) == "PARTIAL"


# -- the two commands must agree ---------------------------------------------


def test_the_eval_and_the_baseline_agree_on_every_shape() -> None:
    """The comparison the baseline exists for requires ONE rule."""
    shapes = [
        [_finding(), _finding(finding_id="f-2")],
        [_finding(), _finding(finding_id="f-1")],          # the same id twice
        [_finding(finding_id=None), _finding(finding_id=None)],
        [_finding(finding_id=None)],
        [_finding(contract_id="OTHER-01")],                # answers nothing
        [],
    ]
    for findings in shapes:
        assert _eval_verdict(findings) == _baseline_verdict(findings), findings


def test_the_baseline_does_not_count_one_finding_twice() -> None:
    """Sharp: the baseline's private copy had no de-duplication at all."""
    findings = [_finding(finding_id="f-1"), _finding(finding_id="f-1")]
    assert _baseline_verdict(findings) == "PARTIAL"


def test_the_baseline_counts_two_id_less_findings_as_two() -> None:
    findings = [
        _finding(finding_id=None, severity="MAJOR"),
        _finding(finding_id=None, severity="MINOR"),
    ]
    assert _baseline_verdict(findings) == "PASS"


def test_a_negative_case_counts_any_finding_as_a_false_positive() -> None:
    """The other half of the rule, unchanged by the refactor."""
    gt = dict(GT)
    gt["should_detect"] = False
    row = judge_case("case-01", gt, [])
    assert row["verdict"] == "PASS"
    row = judge_case("case-01", gt, [_finding()])
    assert row["verdict"] == "FALSE_POSITIVE"


def test_the_shared_verdict_rule_is_the_one_the_eval_uses() -> None:
    findings = [_finding()]
    matched = shared_matched(findings, "COURT-01", "base_pass_head_fail")
    assert shared_verdict(True, findings, matched, 1) == "PASS"
    assert shared_verdict(True, [], [], 1) == "MISS"
    assert shared_verdict(False, [], [], 1) == "PASS"
    assert shared_verdict(False, [_finding()], [_finding()], 1) == "FALSE_POSITIVE"
