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
    # The rule is UNVERIFIED (no evidence can ever pass), but NO differential
    # comparison happened — so both sides stay EMPTY. Reporting
    # "UNVERIFIED -> UNVERIFIED" here would assert that a comparison ran and
    # was inconclusive, which is a different (and false) claim; the coverage
    # page renders the empty pair as "no differential experiment ran".
    assert row["base_result"] == ""
    assert row["head_result"] == ""
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
        # "" is the fourth legitimate value: no differential ran for this
        # rule, which is NOT the same as a side that came back inconclusive.
        assert row["base_result"] in ("", "PASS", "FAIL", "UNVERIFIED")
        assert row["head_result"] in ("", "PASS", "FAIL", "UNVERIFIED")
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
                "execution_surface": "local_host_no_sandbox",
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


# ── execution surface merge (fail-closed disclosure) ────────────────────


def test_execution_surface_is_empty_when_no_differential_ran() -> None:
    """Absent stays absent: the page must be able to tell "no experiment"
    apart from "ran inside a sandbox"."""
    rows = merge_contract_results([
        {"contract_id": "A-1", "result": "PASS", "experiment": "e1"},
    ])
    assert rows[0]["execution_surface"] == ""


def test_execution_surface_reports_the_least_safe_run() -> None:
    """One un-sandboxed run means the change's own code ran on the host.

    Reporting the sibling's sandbox instead would be a false assurance, so the
    merge must fail closed regardless of entry order.
    """
    sandboxed = {"contract_id": "A-1", "result": "PASS", "execution_surface": "docker_sandbox"}
    on_host = {"contract_id": "A-1", "result": "FAIL", "execution_surface": "local_host_no_sandbox"}
    for group in ([sandboxed, on_host], [on_host, sandboxed]):
        rows = merge_contract_results([dict(entry) for entry in group])
        assert rows[0]["execution_surface"] == "local_host_no_sandbox"


def test_execution_surface_treats_an_unattributable_run_as_unsafe() -> None:
    """`unconfirmed` outranks a sandbox claim — the pipeline could not attribute
    the run, and an unknown surface is never rounded to a safe one."""
    rows = merge_contract_results([
        {"contract_id": "A-1", "result": "PASS", "execution_surface": "docker_sandbox"},
        {"contract_id": "A-1", "result": "PASS", "execution_surface": "unconfirmed"},
    ])
    assert rows[0]["execution_surface"] == "unconfirmed"


def test_execution_surface_passes_an_unknown_value_through() -> None:
    """A surface this build has never heard of is reported verbatim, and the
    pick stays deterministic (sorted) so the merge remains pure."""
    rows = merge_contract_results([
        {"contract_id": "A-1", "result": "PASS", "execution_surface": "wasm_sandbox"},
        {"contract_id": "A-1", "result": "PASS", "execution_surface": "quantum_sandbox"},
    ])
    assert rows[0]["execution_surface"] == "quantum_sandbox"


def test_execution_surface_is_blank_not_missing_on_every_row() -> None:
    """It is a canonical field: present on every row, so consumers never have
    to distinguish `None` from `""`."""
    rows = merge_contract_results([
        {"contract_id": "A-1", "result": "PASS"},
        {"contract_id": "B-1", "result": "FAIL", "execution_surface": "docker_sandbox"},
    ])
    assert "execution_surface" in CANONICAL_FIELDS
    for row in rows:
        assert isinstance(row["execution_surface"], str)


# ── execution surface in the HTML report ────────────────────────────────


def _render_report(matrix: dict[str, Any]) -> str:
    from evidence.report import render_verification_report

    return render_verification_report(
        repo="r", base_ref="base", head_ref="head",
        matrix=matrix, findings=[], errors=[], generated_at="2026-01-01 00:00:00 UTC",
    )


def test_report_shows_the_differential_and_where_it_ran() -> None:
    """The downloadable report is the artefact people attach to a PR, so the
    base/head verdict and the execution surface must be in it — not only in
    the web UI."""
    matrix = build_matrix_node(_state_fixture())["matrix"]
    html = _render_report(matrix)
    assert "Differential" in html
    assert "PASS → FAIL" in html
    assert "local_host_no_sandbox" in html


def test_report_says_not_run_instead_of_implying_a_pass() -> None:
    """A row with no differential must not render as a green comparison."""
    rows = merge_contract_results([
        {"contract_id": "A-1", "result": "PASS", "requirement_summary": "r"},
    ])
    html = _render_report({"rows": rows})
    assert "not run" in html
    assert "docker_sandbox" not in html


# ── "no differential ran" vs "differential came back inconclusive" ───────


def test_no_differential_leaves_both_sides_empty_not_unverified() -> None:
    """These two situations must never collapse into one another.

    A rule with no base/head comparison and a rule whose comparison was
    inconclusive both end up UNVERIFIED overall — but only the second one had
    a comparison. Rendering the first as `UNVERIFIED -> UNVERIFIED` tells the
    reader a differential ran, which is exactly the kind of unearned claim the
    coverage page is supposed to avoid.
    """
    rows = merge_contract_results([_meta("PLAIN-01")])
    row = _row(rows, "PLAIN-01")
    assert (row["base_result"], row["head_result"]) == ("", "")
    assert row["result"] == "UNVERIFIED"  # the OVERALL verdict is unchanged


def test_an_inconclusive_differential_still_reports_both_sides() -> None:
    """The counterpart lock: a real comparison that resolved to UNVERIFIED on
    both sides must still say so, rather than looking like "never ran"."""
    rows = merge_contract_results([
        {
            "contract_id": "FLAKY-01",
            "result": "UNVERIFIED",
            "experiment": "DIFF-01",
            "base_result": "UNVERIFIED",
            "head_result": "UNVERIFIED",
        },
    ])
    row = _row(rows, "FLAKY-01")
    assert (row["base_result"], row["head_result"]) == ("UNVERIFIED", "UNVERIFIED")


def test_a_one_sided_differential_keeps_the_side_that_ran() -> None:
    """Half a comparison is still a fact: the observed side must survive while
    the unobserved one stays empty."""
    rows = merge_contract_results([
        {
            "contract_id": "HALF-01",
            "result": "UNVERIFIED",
            "experiment": "DIFF-01",
            "base_result": "PASS",
        },
    ])
    row = _row(rows, "HALF-01")
    assert row["base_result"] == "PASS"
    assert row["head_result"] == ""
