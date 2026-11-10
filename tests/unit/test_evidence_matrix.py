"""Evidence: the requirement-to-evidence matrix ported from the original
unrelated-history branch (docs/p1/README.md) behaves as the old branch
relied on.

The two contracts are chosen so exactly one side is covered by a finding:
the FAIL row must name the *worst* finding by severity (BLOCKER beats
MAJOR), the PASS row must keep the "verified" wording, and the summary
counts must follow the rows.
"""

from typing import Any

from evidence.matrix import build_evidence_matrix


def _contracts() -> list[dict[str, Any]]:
    return [
        {
            "id": "C001-auth-boundary",
            "requirement": "changeEmail needs auth",
            "checker_type": "static_check",
        },
        {
            "id": "C002-rate-limit",
            "requirement": "rate limiter kicks in",
            "checker_type": "static_check",
        },
    ]


def _findings() -> list[dict[str, Any]]:
    return [
        {
            "id": "F-major-001",
            "contract_id": "C001-major-noise",
            "severity": "MAJOR",
            "description": "unrelated major",
            "source": "static_analysis",
        },
        {
            "id": "F-blocker-002",
            "contract_id": "C001-blocker-hit",
            "severity": "BLOCKER",
            "description": "auth missing on changeEmail",
            "source": "differential_test",
        },
    ]


def test_the_worst_finding_wins_and_names_its_capsule() -> None:
    matrix = build_evidence_matrix(_contracts(), _findings(), [])
    by_id = {row["contract_id"]: row for row in matrix["rows"]}

    fail_row = by_id["C001-auth-boundary"]
    assert fail_row["result"] == "FAIL"
    assert "F-blocker-002" in fail_row["evidence"]
    assert "auth missing on changeEmail" in fail_row["evidence"]
    # the experiment tracks the FIRST finding that matched, not the worst one
    assert fail_row["experiment"] == "static_analysis"


def test_an_uncovered_contract_passes_with_the_verified_wording() -> None:
    matrix = build_evidence_matrix(_contracts(), _findings(), [])
    by_id = {row["contract_id"]: row for row in matrix["rows"]}

    pass_row = by_id["C002-rate-limit"]
    assert pass_row["result"] == "PASS"
    assert "verified" in pass_row["evidence"]
    assert pass_row["experiment"] == "differential_test"


def test_the_summary_counts_follow_the_rows() -> None:
    matrix = build_evidence_matrix(_contracts(), _findings(), ["X-STATIC_CHECKS-only"])
    assert matrix["total_contracts"] == 2
    assert matrix["passed"] == 1
    assert matrix["failed"] == 1
    assert matrix["unverified"] == 0


def test_changed_symbols_follow_the_checker_type_and_prefix_match() -> None:
    matrix = build_evidence_matrix(
        _contracts(),
        [],
        ["STATIC_CHECKS_run", "c001_lowercase_helper", "unrelated_symbol"],
    )
    by_id = {row["contract_id"]: row for row in matrix["rows"]}

    assert by_id["C001-auth-boundary"]["changed_symbols"] == [
        "STATIC_CHECKS_run",
        "c001_lowercase_helper",
    ]
    assert by_id["C002-rate-limit"]["changed_symbols"] == ["STATIC_CHECKS_run"]
