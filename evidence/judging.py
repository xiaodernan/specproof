"""How a measurement is JUDGED - ONE rule, ONE place.

Two commands judge a case's findings:

- ``specproof eval`` judges the tool's own measurements;
- ``specproof baseline`` judges a baseline model's findings, so the two
  can be compared.

The baseline's docstring says it applies "the SAME judging rules as
specproof eval" - and then wrote its own copy. The two copies drifted
apart, measured on the SAME findings (ledger #419):

- a finding **without an id**: the eval dropped every id-less finding
  after the first (they all share the key ``""``), so two real findings
  counted as one;
- a finding reported **twice under the same id**: the eval counted it
  once (right - it is one finding), the baseline counted it twice.

The second is a deliberate rule: a finding reported twice is ONE
finding, and counting it twice would let it satisfy a
``min_findings: 2`` expectation on its own.

The first was a bug: a finding with no id cannot be proven to be a
duplicate, so it must be KEPT. Only a finding that CARRIES an id can be
recognised as the same finding twice.

This module is the single home of both rules. The eval re-exports them
(so its existing import paths keep working); the baseline uses them
directly. There is no second copy to drift.
"""

from __future__ import annotations

from typing import Any

__all__ = ["matched_findings", "verdict_for"]


def matched_findings(
    findings: list[dict[str, Any]],
    expected_contract: str,
    expected_evidence: str,
) -> list[dict[str, Any]]:
    """The findings that answer THIS case's expectation.

    Two ways a finding can answer it: it carries the expected contract id,
    or its evidence type (or its id) names the expected evidence. The
    second way is why a case whose findings do not carry the expected
    contract id is not automatically a miss.

    A finding reported twice under the SAME id is one finding: it is
    counted once, so it cannot satisfy a ``min_findings`` expectation on
    its own. A finding with NO id is also one finding, but it cannot be
    recognised as a repeat - so it is KEPT (ledger #419).
    """
    matched: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for f in findings:
        fid = f.get("contract_id", "")
        answers = bool(
            expected_contract and fid == expected_contract
            or expected_evidence and (
                expected_evidence in f.get("evidence_type", "")
                or expected_evidence in fid.lower()
            )
        )
        if not answers:
            continue
        finding_id = f.get("id", "")
        if finding_id:
            if finding_id in seen_ids:
                continue
            seen_ids.add(finding_id)
        matched.append(f)
    return matched


def verdict_for(
    should_detect: bool,
    findings: list[dict[str, Any]],
    matched: list[dict[str, Any]],
    min_findings: int,
) -> str:
    """The verdict ONE measurement earns.

    A positive case is detected when the expected contract was found; a
    negative case is a false positive when the pipeline confirmed
    ANYTHING at all (not just a match against an expectation it does not
    have — see split.json: max_findings = 0).
    """
    if should_detect:
        if len(matched) >= min_findings:
            return "PASS"
        if matched:
            return "PARTIAL"
        return "MISS"
    return "FALSE_POSITIVE" if findings else "PASS"
