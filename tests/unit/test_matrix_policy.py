"""Unit tests for agent.matrix_policy — the pure matrix merge rule (§14.1).

No network, no I/O: merge_contract_results is dict-in / dict-out, so every
case here is a plain function call. Covers the priority merge, the
missing-experiment UNVERIFIED downgrade, order-independent contention and
the canonical field completeness, plus the build_matrix node wiring that
keeps the legacy matrix shape green for existing consumers.
"""
from __future__ import annotations

import itertools
from typing import Any

from agent.matrix_policy import (
    CANONICAL_FIELDS,
    NEXT_ACTION_FAIL,
    NEXT_ACTION_PASS,
    NEXT_ACTION_UNVERIFIED,
    UNVERIFIED_INCONCLUSIVE_REASON,
    UNVERIFIED_NO_EXPERIMENT_REASON,
    merge_contract_results,
)
from agent.nodes.build_matrix import build_matrix_node


def _row(rows: list[dict[str, Any]], contract_id: str) -> dict[str, Any]:
    for row in rows:
        if row["contract_id"] == contract_id:
            return row
    raise AssertionError(f"row {contract_id!r} missing from {rows}")


def _meta(
    contract_id: str, requirement: str = "需求摘要", version: int = 1
) -> dict[str, Any]:
    return {
        "contract_id": contract_id,
        "contract_version": version,
        "requirement_summary": requirement,
        "changed_symbols": [],
    }


# -- priority merge -------------------------------------------------------


def test_fail_beats_pass_beats_unverified_in_any_order() -> None:
    """FAIL wins over PASS and UNVERIFIED no matter which node wrote last."""
    entries = [
        _meta("AUTH-01"),
        {
            "contract_id": "AUTH-01",
            "result": "UNVERIFIED",
            "experiment": "java_source_diff",
        },
        {
            "contract_id": "AUTH-01",
            "result": "PASS",
            "experiment": "probe_differential",
            "evidence_ref": "sha256:pass",
        },
        {
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "experiment": "generated_test_differential",
            "evidence_ref": "sha256:fail",
        },
    ]
    for order in itertools.permutations(entries):
        rows = merge_contract_results(list(order))
        row = _row(rows, "AUTH-01")
        assert row["result"] == "FAIL"
        assert "sha256:fail" in row["evidence_refs"]
        assert "generated_test_differential" in row["experiment_ids"]


def test_pass_beats_unverified() -> None:
    rows = merge_contract_results([
        _meta("UNIQUE-01"),
        {
            "contract_id": "UNIQUE-01",
            "result": "UNVERIFIED",
            "experiment": "java_source_diff",
        },
        {
            "contract_id": "UNIQUE-01",
            "result": "PASS",
            "experiment": "generated_test_differential",
            "evidence_ref": "sha256:ok",
        },
    ])
    row = _row(rows, "UNIQUE-01")
    assert row["result"] == "PASS"
    assert row["next_action"] == NEXT_ACTION_PASS
    assert row["unverified_reason"] == ""


def test_unknown_result_values_never_beat_unverified() -> None:
    rows = merge_contract_results([
        {
            "contract_id": "AUTH-01",
            "result": "WAT",
            "experiment": "probe_differential",
        },
    ])
    assert _row(rows, "AUTH-01")["result"] == "UNVERIFIED"


# -- missing experiment -> UNVERIFIED + reason ----------------------------


def test_contract_without_any_experiment_is_unverified_with_reason() -> None:
    rows = merge_contract_results([
        {
            "contract_id": "TRANSACTION-01",
            "contract_version": 2,
            "requirement_summary": "事务原子性",
            "changed_symbols": ["TxService"],
        },
    ])
    row = _row(rows, "TRANSACTION-01")
    assert row["result"] == "UNVERIFIED"
    assert row["unverified_reason"] == UNVERIFIED_NO_EXPERIMENT_REASON
    assert row["next_action"] == NEXT_ACTION_UNVERIFIED
    assert row["experiment_ids"] == []
    assert row["evidence_refs"] == []
    assert row["min_evidence_level"] == "none"
    assert row["base_result"] == "UNVERIFIED"
    assert row["head_result"] == "UNVERIFIED"
    assert row["attribution"] == "unknown"
    assert row["contract_version"] == 2
    assert row["requirement_summary"] == "事务原子性"
    assert row["changed_symbols"] == ["TxService"]


def test_experiment_that_stayed_unverified_keeps_inconclusive_reason() -> None:
    rows = merge_contract_results([
        _meta("MIGRATION-01"),
        {
            "contract_id": "MIGRATION-01",
            "result": "UNVERIFIED",
            "experiment": "java_source_diff",
        },
    ])
    row = _row(rows, "MIGRATION-01")
    assert row["result"] == "UNVERIFIED"
    assert row["unverified_reason"] == UNVERIFIED_INCONCLUSIVE_REASON
    assert row["experiment_ids"] == ["java_source_diff"]


# -- deterministic contention ----------------------------------------------


def test_contention_merge_is_order_independent() -> None:
    """The same multiset of competing entries yields byte-identical rows."""
    entries = [
        _meta("AUTH-01", version=1),
        _meta("UNIQUE-01", version=3),
        {
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "experiment": "java_source_diff",
            "evidence_ref": "static-f-1",
        },
        {
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "experiment": "generated_test_differential",
            "evidence_ref": "sha256:runtime",
            "attribution": "head",
            "base_result": "PASS",
            "head_result": "FAIL",
        },
        {
            "contract_id": "AUTH-01",
            "result": "PASS",
            "experiment": "probe_differential",
            "evidence_ref": "sha256:pass",
        },
        {
            "contract_id": "UNIQUE-01",
            "result": "PASS",
            "experiment": "generated_test_differential",
            "evidence_ref": "sha256:unique",
        },
    ]
    reference = merge_contract_results(entries)
    assert len(reference) == 2
    for order in itertools.permutations(entries):
        assert merge_contract_results(list(order)) == reference
    auth = _row(reference, "AUTH-01")
    assert auth["result"] == "FAIL"
    # Runtime evidence wins the attribution tie among the two FAIL entries.
    assert auth["attribution"] == "head"
    assert auth["evidence_refs"] == ["sha256:pass", "sha256:runtime", "static-f-1"]
    assert auth["experiment_ids"] == [
        "generated_test_differential",
        "java_source_diff",
        "probe_differential",
    ]


# -- base/head verdicts and evidence levels ---------------------------------


def test_base_head_verdicts_merge_per_side() -> None:
    rows = merge_contract_results([
        {
            "contract_id": "AUTH-01",
            "base_result": "PASS",
            "head_result": "FAIL",
            "experiment": "DIFF-01",
            "attribution": "head",
        },
        {
            "contract_id": "AUTH-01",
            "base_result": "FAIL",
            "head_result": "PASS",
            "experiment": "DIFF-01",
            "attribution": "base",
        },
    ])
    row = _row(rows, "AUTH-01")
    assert row["base_result"] == "FAIL"
    assert row["head_result"] == "FAIL"


def test_min_evidence_level_is_weakest_attached_ref() -> None:
    rows = merge_contract_results([
        {
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "experiment": "java_source_diff",
            "evidence_ref": "static-f-1",
        },
        {
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "experiment": "generated_test_differential",
            "evidence_ref": "sha256:runtime",
        },
    ])
    row = _row(rows, "AUTH-01")
    assert row["min_evidence_level"] == "static"


def test_fail_row_gets_fail_next_action_and_head_attribution_default() -> None:
    rows = merge_contract_results([
        {
            "contract_id": "OPENAPI-01",
            "result": "FAIL",
            "experiment": "java_source_diff",
            "evidence_ref": "openapi-f-1",
        },
    ])
    row = _row(rows, "OPENAPI-01")
    assert row["result"] == "FAIL"
    assert row["next_action"] == NEXT_ACTION_FAIL
    assert row["attribution"] == "head"
    assert row["unverified_reason"] == ""


# -- field completeness ------------------------------------------------------


def test_every_row_carries_all_canonical_fields() -> None:
    rows = merge_contract_results([
        _meta("AUTH-01"),
        {
            "contract_id": "AUTH-01",
            "result": "FAIL",
            "experiment": "generated_test_differential",
            "evidence_ref": "sha256:ab",
            "attribution": "head",
            "base_result": "PASS",
            "head_result": "FAIL",
        },
        _meta("UNIQUE-01"),
    ])
    assert [row["contract_id"] for row in rows] == ["AUTH-01", "UNIQUE-01"]
    for row in rows:
        assert set(CANONICAL_FIELDS) <= set(row)
        assert set(row["contract_id"]) and isinstance(row["contract_id"], str)
        assert isinstance(row["contract_version"], int)
        assert isinstance(row["requirement_summary"], str)
        assert isinstance(row["changed_symbols"], list)
        assert isinstance(row["experiment_ids"], list)
        assert row["base_result"] in ("PASS", "FAIL", "UNVERIFIED")
        assert row["head_result"] in ("PASS", "FAIL", "UNVERIFIED")
        assert isinstance(row["attribution"], str)
        assert isinstance(row["evidence_refs"], list)
        assert row["min_evidence_level"] in ("runtime", "static", "none")
        assert isinstance(row["unverified_reason"], str)
        assert isinstance(row["next_action"], str)
        assert row["result"] in ("PASS", "FAIL", "UNVERIFIED")
    auth = _row(rows, "AUTH-01")
    assert auth["result"] == "FAIL"
    assert auth["base_result"] == "PASS"
    assert auth["head_result"] == "FAIL"
    assert auth["min_evidence_level"] == "runtime"


# -- hygiene ------------------------------------------------------------------


def test_empty_entries_and_missing_contract_ids_are_ignored() -> None:
    assert merge_contract_results([]) == []
    assert merge_contract_results([
        {"result": "FAIL", "experiment": "probe_differential"},
        {"contract_id": "", "result": "PASS"},
        {"contract_id": "   ", "result": "PASS"},
    ]) == []


# -- build_matrix node wiring (legacy consumers stay green) --------------------


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
            {
                "contract_id": "GHOST-01",
                "result": "FAIL",
                "experiment": "probe_differential",
                "evidence_ref": "sha256:ghost",
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
                "contract_id": "",
                "description": "无契约归属的发现",
                "type": "heuristic",
                "source": "review_court",
                "id": "EXTRA-F-1",
                "severity": "MAJOR",
            },
        ],
        "changed_symbols": ["AuthController", "AuthService", "UserService"],
    }


def test_node_keeps_legacy_matrix_shape_and_counts() -> None:
    matrix = build_matrix_node(_state_fixture())["matrix"]
    assert matrix["total_contracts"] == 3
    assert matrix["total_rows"] == 4
    assert matrix["passed"] == 1
    assert matrix["failed"] == 2
    assert matrix["unverified"] == 1

    rows = matrix["rows"]
    # Compiled contracts keep their order; finding-only rows follow.
    assert [row["contract_id"] for row in rows] == [
        "AUTH-01",
        "UNIQUE-01",
        "TRANSACTION-01",
        "EXTRA",
    ]
    auth = _row(rows, "AUTH-01")
    assert auth["result"] == "FAIL"
    # legacy keys stay populated for existing consumers
    assert auth["requirement"] == "未认证请求必须 401"
    assert auth["checker_type"] == "http"
    assert auth["experiment"] == "DIFF-01"
    assert auth["evidence"] == "sha256:d"
    assert auth["changed_symbols"] == ["AuthController", "AuthService"]
    # canonical §14.1 keys ride along
    assert auth["experiment_ids"] == ["DIFF-01", "generated_test_differential"]
    assert auth["base_result"] == "PASS"
    assert auth["head_result"] == "FAIL"
    assert auth["attribution"] == "head"
    assert auth["evidence_refs"] == ["sha256:d", "sha256:deadbeef"]
    assert auth["min_evidence_level"] == "runtime"
    assert auth["unverified_reason"] == ""
    assert auth["next_action"] == NEXT_ACTION_FAIL

    unique = _row(rows, "UNIQUE-01")
    assert unique["result"] == "PASS"
    assert unique["contract_version"] == 3
    assert unique["experiment"] == "generated_test_differential"

    transaction = _row(rows, "TRANSACTION-01")
    assert transaction["result"] == "UNVERIFIED"
    assert transaction["experiment"] == "none"
    assert transaction["evidence"] == "—"
    assert transaction["unverified_reason"] == UNVERIFIED_NO_EXPERIMENT_REASON

    extra = _row(rows, "EXTRA")
    assert extra["result"] == "FAIL"
    assert extra["requirement"] == "无契约归属的发现"
    assert extra["checker_type"] == "heuristic"
    assert extra["attribution"] == "head"

    # Ghost results for contracts the pipeline never compiled stay out.
    assert all(row["contract_id"] != "GHOST-01" for row in rows)


def test_node_matrix_still_renders_in_the_html_report() -> None:
    from evidence.report import render_verification_report

    matrix = build_matrix_node(_state_fixture())["matrix"]
    html = render_verification_report(
        repo="r",
        base_ref="base",
        head_ref="head",
        matrix=matrix,
        findings=[],
        errors=[],
    )
    assert "未认证请求必须 401" in html
    assert "邮箱唯一" in html
    assert "sha256:d" in html
