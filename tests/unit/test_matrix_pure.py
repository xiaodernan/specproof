"""Unit tests for the pure matrix build (backlog #2).

Three contracts with the evidence matrix:

- purity: the merge and the node are pure functions — the same input
  produces byte-identical output, repeated calls interleave freely and no
  input dict is ever mutated (no clock, no randomness, no module state);
- completeness: every row carries the complete field set — the canonical
  §14.1 fields, the derived "result", the legacy renderer keys and the
  review-court row fields (severity / confidence / evidence_type / verdict /
  detail / status / source / type / location / evidence_digest / finding_id);
- compatibility: the legacy row projection (the bytes the HTML report and
  the worker/CLI counts read) is unchanged by the field completion, court
  metadata never fabricates or downgrades a verdict, and the renderer
  accepts an explicit caller-supplied timestamp.
"""
from __future__ import annotations

import copy
import itertools
from typing import Any

from agent.matrix_policy import (
    CANONICAL_FIELDS,
    COURT_ROW_FIELDS,
    merge_contract_results,
)
from agent.nodes.build_matrix import (
    COMPLETE_ROW_FIELDS,
    LEGACY_ROW_FIELDS,
    build_matrix_node,
)
from evidence.report import render_verification_report

#: The legacy row projection — everything the pre-backlog-2 consumers
#: (HTML report, worker counts, CLI summary, existing matrix tests) read.
_LEGACY_PROJECTION = (
    "contract_id",
    "contract_version",
    "requirement_summary",
    "requirement",
    "checker_type",
    "experiment",
    "evidence",
    "changed_symbols",
    "experiment_ids",
    "base_result",
    "head_result",
    "attribution",
    "evidence_refs",
    "min_evidence_level",
    "unverified_reason",
    "next_action",
    "result",
)


def _state_fixture() -> dict[str, Any]:
    return {
        "contracts": [
            {
                "id": "AUTH-01",
                "requirement": "未认证请求必须 401",
                "checker_type": "http",
                "version": 1,
            },
            {
                "id": "UNIQUE-01",
                "requirement": "邮箱唯一",
                "checker_type": "sql",
                "version": 3,
            },
            {
                "id": "TRANSACTION-01",
                "requirement": "事务原子",
                "checker_type": "sql",
                "version": 1,
            },
        ],
        "contract_results": [
            {
                "contract_id": "AUTH-01",
                "result": "FAIL",
                "experiment": "generated_test_differential",
                "evidence_ref": "sha256:deadbeef",
            },
            {
                "contract_id": "UNIQUE-01",
                "result": "PASS",
                "experiment": "generated_test_differential",
                "evidence_ref": "sha256:beef",
            },
        ],
        "diff_results": [
            {
                "contract_id": "AUTH-01",
                "experiment_id": "DIFF-01",
                "verdict": "REGRESSION",
                "base_exit_code": 0,
                "head_exit_code": 1,
                "evidence_digest": "sha256:d",
            },
        ],
        "confirmed_findings": [
            {
                "id": "COURT-AUTH-01",
                "contract_id": "AUTH-01",
                "severity": "BLOCKER",
                "type": "differential_regression",
                "description": "未认证修改邮箱成功 (Base 401 -> Head 200)",
                "evidence_type": "differential_execution",
                "confidence": 0.95,
                "source": "differential",
                "status": "confirmed",
                "diff_verdict": "REGRESSION",
                "location": "SecurityConfig.java:12",
                "evidence_digest": "sha256:court",
            },
            {
                "id": "EXTRA-F-1",
                "contract_id": "",
                "description": "无契约归属的发现",
                "type": "heuristic",
                "source": "review_court",
                "severity": "MAJOR",
                "confidence": 0.7,
                "evidence_type": "heuristic",
                "status": "confirmed",
            },
        ],
        "changed_symbols": ["AuthController", "AuthService", "UserService"],
    }


def _row(rows: list[dict[str, Any]], contract_id: str) -> dict[str, Any]:
    for row in rows:
        if row["contract_id"] == contract_id:
            return row
    raise AssertionError(f"row {contract_id!r} missing from {rows}")


def _projection(row: dict[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in _LEGACY_PROJECTION}


# ── field-set contract ──────────────────────────────────────────────────


def test_complete_field_set_constant_covers_every_contract() -> None:
    """COMPLETE_ROW_FIELDS = canonical (§14.1 + court) + result + legacy."""
    assert CANONICAL_FIELDS[-len(COURT_ROW_FIELDS):] == COURT_ROW_FIELDS
    assert COMPLETE_ROW_FIELDS == CANONICAL_FIELDS + ("result",) + LEGACY_ROW_FIELDS


def test_every_row_carries_complete_field_set() -> None:
    matrix = build_matrix_node(_state_fixture())["matrix"]
    assert len(matrix["rows"]) == 4
    for row in matrix["rows"]:
        assert set(COMPLETE_ROW_FIELDS) <= set(row)
        assert isinstance(row["contract_id"], str) and row["contract_id"]
        assert isinstance(row["severity"], str)
        assert isinstance(row["confidence"], float)
        assert 0.0 <= row["confidence"] <= 1.0
        assert isinstance(row["evidence_type"], str)
        assert isinstance(row["verdict"], str)
        assert isinstance(row["detail"], str)
        assert isinstance(row["status"], str)
        assert isinstance(row["source"], str)
        assert isinstance(row["type"], str)
        assert isinstance(row["location"], str)
        assert isinstance(row["evidence_digest"], str)
        assert isinstance(row["finding_id"], str)


# ── purity: same input -> same output, no side effects ──────────────────


def test_merge_is_pure_and_does_not_mutate_entries() -> None:
    entries = [
        {
            "contract_id": "AUTH-01",
            "contract_version": 1,
            "requirement_summary": "r",
            "changed_symbols": [],
        },
        {
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "experiment": "e",
            "evidence_ref": "sha256:x",
        },
        {
            "contract_id": "AUTH-01",
            "severity": "MAJOR",
            "confidence": 0.5,
            "status": "confirmed",
            "finding_id": "F-1",
        },
    ]
    before = copy.deepcopy(entries)
    first = merge_contract_results(entries)
    second = merge_contract_results(entries)
    assert first == second
    assert entries == before


def test_node_is_pure_and_does_not_mutate_state() -> None:
    state = _state_fixture()
    before = copy.deepcopy(state)
    first = build_matrix_node(dict(state))
    second = build_matrix_node(dict(state))
    assert first == second
    assert first == build_matrix_node(_state_fixture())
    assert state == before


def test_court_field_winner_is_order_independent() -> None:
    """Two findings for one contract: the strongest (BLOCKER) wins in ANY
    entry order — no last-write-wins, no randomness."""
    entries = [
        {
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "experiment": "e",
            "evidence_ref": "sha256:x",
        },
        {
            "contract_id": "AUTH-01",
            "severity": "MAJOR",
            "confidence": 0.6,
            "finding_id": "F-MAJOR",
            "status": "confirmed",
        },
        {
            "contract_id": "AUTH-01",
            "severity": "BLOCKER",
            "confidence": 0.9,
            "finding_id": "F-BLOCKER",
            "status": "confirmed",
        },
    ]
    reference = merge_contract_results(entries)
    assert reference[0]["severity"] == "BLOCKER"
    assert reference[0]["finding_id"] == "F-BLOCKER"
    assert reference[0]["confidence"] == 0.9
    for order in itertools.permutations(entries):
        assert merge_contract_results(list(order)) == reference


# ── court field values per row kind ─────────────────────────────────────


def test_known_contract_row_carries_its_finding_court_fields() -> None:
    matrix = build_matrix_node(_state_fixture())["matrix"]
    auth = _row(matrix["rows"], "AUTH-01")
    assert auth["severity"] == "BLOCKER"
    assert auth["confidence"] == 0.95
    assert auth["evidence_type"] == "differential_execution"
    assert auth["verdict"] == "REGRESSION"
    assert auth["detail"] == "未认证修改邮箱成功 (Base 401 -> Head 200)"
    assert auth["status"] == "confirmed"
    assert auth["source"] == "differential"
    assert auth["type"] == "differential_regression"
    assert auth["location"] == "SecurityConfig.java:12"
    assert auth["evidence_digest"] == "sha256:court"
    assert auth["finding_id"] == "COURT-AUTH-01"


def test_pass_and_unverified_rows_have_neutral_court_fields() -> None:
    matrix = build_matrix_node(_state_fixture())["matrix"]
    unique = _row(matrix["rows"], "UNIQUE-01")
    transaction = _row(matrix["rows"], "TRANSACTION-01")
    assert unique["result"] == "PASS"
    assert transaction["result"] == "UNVERIFIED"
    for row in (unique, transaction):
        assert row["severity"] == ""
        assert row["confidence"] == 0.0
        assert row["evidence_type"] == ""
        assert row["verdict"] == ""
        assert row["detail"] == ""
        assert row["status"] == ""
        assert row["source"] == ""
        assert row["type"] == ""
        assert row["location"] == ""
        assert row["evidence_digest"] == ""
        assert row["finding_id"] == ""


def test_extra_finding_row_carries_full_court_fields() -> None:
    matrix = build_matrix_node(_state_fixture())["matrix"]
    extra = _row(matrix["rows"], "EXTRA")
    assert extra["result"] == "FAIL"
    assert extra["severity"] == "MAJOR"
    assert extra["confidence"] == 0.7
    assert extra["evidence_type"] == "heuristic"
    assert extra["verdict"] == ""
    assert extra["detail"] == "无契约归属的发现"
    assert extra["status"] == "confirmed"
    assert extra["source"] == "review_court"
    assert extra["type"] == "heuristic"
    assert extra["finding_id"] == "EXTRA-F-1"


def test_court_spelling_fallbacks_are_accepted() -> None:
    """The merge reads the review-court spellings (diff_verdict /
    description / id) when the row-level names are absent."""
    rows = merge_contract_results([
        {"contract_id": "C-01", "result": "FAIL", "experiment": "e"},
        {
            "contract_id": "C-01",
            "severity": "MINOR",
            "diff_verdict": "REGRESSION",
            "description": "d-text",
            "id": "F-9",
        },
    ])
    row = rows[0]
    assert row["verdict"] == "REGRESSION"
    assert row["detail"] == "d-text"
    assert row["finding_id"] == "F-9"


def test_confidence_is_clamped_to_unit_interval() -> None:
    base = {"contract_id": "C-01", "result": "FAIL", "experiment": "e"}
    rows = merge_contract_results([
        base,
        {"contract_id": "C-01", "severity": "MAJOR", "confidence": 3.5, "finding_id": "F-1"},
    ])
    assert rows[0]["confidence"] == 1.0
    rows = merge_contract_results([
        base,
        {"contract_id": "C-01", "severity": "MAJOR", "confidence": -2.0, "finding_id": "F-1"},
    ])
    assert rows[0]["confidence"] == 0.0
    rows = merge_contract_results([
        base,
        {"contract_id": "C-01", "severity": "MAJOR", "confidence": "high", "finding_id": "F-1"},
    ])
    assert rows[0]["confidence"] == 0.0


# ── compatibility: the legacy byte shape stays put ──────────────────────


def test_court_metadata_never_changes_verdict_experiments_or_refs() -> None:
    """A verdict-free court-metadata entry only adds fields — it can never
    fabricate or downgrade a verdict or disturb experiment/evidence merge."""
    rows = merge_contract_results([
        {
            "contract_id": "AUTH-01",
            "contract_version": 1,
            "requirement_summary": "r",
            "changed_symbols": [],
        },
        {
            "contract_id": "AUTH-01",
            "result": "PASS",
            "experiment": "e1",
            "evidence_ref": "sha256:x",
        },
        {
            "contract_id": "AUTH-01",
            "severity": "MAJOR",
            "confidence": 0.5,
            "status": "confirmed",
            "finding_id": "F-1",
        },
    ])
    row = rows[0]
    assert row["result"] == "PASS"
    assert row["experiment_ids"] == ["e1"]
    assert row["evidence_refs"] == ["sha256:x"]
    assert row["attribution"] == "none"
    assert row["severity"] == "MAJOR"
    assert row["finding_id"] == "F-1"


def test_legacy_projection_unchanged_by_court_field_completion() -> None:
    """Adding a confirmed finding for a known contract must not move a
    single legacy byte of any row — only the new court fields appear."""
    with_finding = build_matrix_node(_state_fixture())["matrix"]
    state_without = _state_fixture()
    state_without["confirmed_findings"] = [
        f for f in state_without["confirmed_findings"] if not f.get("contract_id")
    ]
    without_finding = build_matrix_node(state_without)["matrix"]

    rows_with = {row["contract_id"]: row for row in with_finding["rows"]}
    rows_without = {row["contract_id"]: row for row in without_finding["rows"]}
    assert list(rows_with) == list(rows_without)
    assert with_finding["total_rows"] == without_finding["total_rows"]
    assert with_finding["passed"] == without_finding["passed"]
    assert with_finding["failed"] == without_finding["failed"]
    assert with_finding["unverified"] == without_finding["unverified"]

    for cid, row in rows_with.items():
        assert _projection(row) == _projection(rows_without[cid])

    # The only difference is the new court fields on the finding's row.
    auth_with = rows_with["AUTH-01"]
    auth_without = rows_without["AUTH-01"]
    assert auth_with["finding_id"] == "COURT-AUTH-01"
    assert auth_without["finding_id"] == ""


def test_matrix_counts_and_row_order_unchanged() -> None:
    matrix = build_matrix_node(_state_fixture())["matrix"]
    assert matrix["total_contracts"] == 3
    assert matrix["total_rows"] == 4
    assert matrix["passed"] == 1
    assert matrix["failed"] == 2
    assert matrix["unverified"] == 1
    assert [row["contract_id"] for row in matrix["rows"]] == [
        "AUTH-01",
        "UNIQUE-01",
        "TRANSACTION-01",
        "EXTRA",
    ]


# ── renderer: explicit caller-supplied timestamp ────────────────────────


def test_render_is_deterministic_with_explicit_generated_at() -> None:
    matrix = build_matrix_node(_state_fixture())["matrix"]
    before = copy.deepcopy(matrix)
    common: dict[str, Any] = {
        "repo": "r",
        "base_ref": "base",
        "head_ref": "head",
        "matrix": matrix,
        "findings": [],
        "errors": [],
    }
    html_a = render_verification_report(**common, generated_at="2026-08-20 00:00:00 UTC")
    html_b = render_verification_report(**common, generated_at="2026-08-20 00:00:00 UTC")
    html_c = render_verification_report(**common, generated_at="2026-08-21 00:00:00 UTC")
    assert html_a == html_b
    assert html_a != html_c
    assert "2026-08-20 00:00:00 UTC" in html_a
    assert "2026-08-21 00:00:00 UTC" in html_c
    assert matrix == before  # the renderer must not mutate its inputs


def test_render_default_timestamp_path_still_renders() -> None:
    html = render_verification_report(
        repo="r", base_ref="b", head_ref="h", matrix={"rows": []}, findings=[]
    )
    assert "Generated:" in html


def test_html_legacy_cells_unchanged_by_new_fields() -> None:
    """The six legacy table cells the HTML report reads render exactly as
    before the field completion (row count included)."""
    matrix = build_matrix_node(_state_fixture())["matrix"]
    html = render_verification_report(
        repo="r",
        base_ref="base",
        head_ref="head",
        matrix=matrix,
        findings=[],
        errors=[],
        generated_at="2026-08-20 00:00:00 UTC",
    )
    assert html.count('<tr class="') == 4
    assert "未认证请求必须 401" in html
    assert "邮箱唯一" in html
    assert "事务原子" in html
    assert "无契约归属的发现" in html
    assert "sha256:d" in html
    assert "sha256:beef" in html
