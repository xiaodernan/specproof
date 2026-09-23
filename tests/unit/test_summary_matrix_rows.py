"""The persisted job summary must carry per-requirement matrix rows.

Before this, `_state_summary` wrote only matrix COUNTS, so `GET
/api/v1/jobs/{id}/matrix` had nothing to serve for a real job: the `contracts`
table is written by the demo seeder alone. These tests lock the projection
that fixed it — including that it can never invent a verdict, and that a
truncated row list reports itself instead of quietly under-counting.
"""
from __future__ import annotations

from agent.worker import (
    SUMMARY_MATRIX_ROW_CAP,
    _matrix_rows_for_summary,
    _state_summary,
)


def _row(contract_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "contract_id": contract_id,
        "requirement": f"requirement text for {contract_id}",
        "checker_type": "java_source",
        "result": "FAIL",
        "experiment": "DIFF-01",
        "evidence": "sha256:abc",
        "attribution": "head",
        "base_result": "PASS",
        "head_result": "FAIL",
        "next_action": "阻断合并",
        "severity": "MAJOR",
        "evidence_type": "differential_execution",
        "location": "UserController.java:42",
        "finding_id": "COURT-DIFF-01",
    }
    row.update(overrides)
    return row


class TestMatrixRowsForSummary:
    def test_no_matrix_yields_empty_rows_not_a_fabricated_one(self) -> None:
        assert _matrix_rows_for_summary(None) == {
            "matrix_rows": [],
            "matrix_rows_total": 0,
            "matrix_rows_truncated": False,
        }
        assert _matrix_rows_for_summary({"rows": "not-a-list"})["matrix_rows"] == []

    def test_differential_attribution_survives_the_projection(self) -> None:
        result = _matrix_rows_for_summary(
            {"rows": [_row("AUTH-01")], "total_rows": 1}
        )
        assert result["matrix_rows_total"] == 1
        assert result["matrix_rows_truncated"] is False
        (kept,) = result["matrix_rows"]
        # The three fields that used to die at the persistence boundary.
        assert kept["base_result"] == "PASS"
        assert kept["head_result"] == "FAIL"
        assert kept["attribution"] == "head"
        assert kept["result"] == "FAIL"

    def test_rows_without_a_contract_id_are_dropped(self) -> None:
        result = _matrix_rows_for_summary(
            {"rows": [_row(""), _row("  "), "junk", _row("TX-01")], "total_rows": 4}
        )
        assert [row["contract_id"] for row in result["matrix_rows"]] == ["TX-01"]

    def test_only_the_declared_keys_are_carried(self) -> None:
        (kept,) = _matrix_rows_for_summary(
            {"rows": [_row("AUTH-01", changed_symbols=["A", "B"], noise="x")]
             }
        )["matrix_rows"]
        assert "changed_symbols" not in kept
        assert "noise" not in kept

    def test_long_text_is_cut_and_still_marked_as_truncated(self) -> None:
        (kept,) = _matrix_rows_for_summary(
            {"rows": [_row("AUTH-01", requirement="很长" * 500)]}
        )["matrix_rows"]
        assert kept["requirement"].endswith("…")
        assert len(kept["requirement"]) <= 401

    def test_over_cap_rows_are_reported_not_silently_dropped(self) -> None:
        rows = [_row(f"C-{index}") for index in range(SUMMARY_MATRIX_ROW_CAP + 5)]
        result = _matrix_rows_for_summary({"rows": rows, "total_rows": len(rows)})
        assert len(result["matrix_rows"]) == SUMMARY_MATRIX_ROW_CAP
        assert result["matrix_rows_total"] == SUMMARY_MATRIX_ROW_CAP + 5
        assert result["matrix_rows_truncated"] is True

    def test_total_falls_back_to_the_row_list_when_the_matrix_omits_it(self) -> None:
        result = _matrix_rows_for_summary({"rows": [_row("AUTH-01")]})
        assert result["matrix_rows_total"] == 1


class TestStateSummaryCarriesTheMatrix:
    def test_summary_embeds_rows_and_keeps_pipeline_counts(self) -> None:
        state = {
            "matrix": {
                "rows": [_row("AUTH-01")],
                "total_rows": 1,
                "passed": 0,
                "failed": 1,
                "unverified": 0,
            },
            "contracts": [{"id": "AUTH-01"}],
            "confirmed_findings": [],
            "errors": [],
        }
        summary = _state_summary(state, "BLOCKED")
        assert summary["matrix_rows_total"] == 1
        assert summary["matrix_rows"][0]["contract_id"] == "AUTH-01"
        # Counts still come from the verdict evaluator, never from the rows.
        assert summary["matrix_failed"] == 1

    def test_summary_is_json_serialisable(self) -> None:
        import json

        summary = _state_summary(
            {"matrix": {"rows": [_row("AUTH-01")]}, "contracts": [],
             "confirmed_findings": [], "errors": []},
            "BLOCKED",
        )
        assert json.loads(json.dumps(summary, default=str))["matrix_rows"]
