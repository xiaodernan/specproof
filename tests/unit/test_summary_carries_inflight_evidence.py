"""#262 — the persisted job summary + matrix rows must carry the in-flight evidence.

#261 made behavioral_evidence / db_violation_evidence / db_state_detail reach
confirmed_findings + court_audit + the HTML file. But the API/frontend reads the
PERSISTED JOB SUMMARY, and every projection between confirmed_findings and that
summary is a fixed-key dict that silently dropped the new fields:

    confirmed_findings
      -> build_matrix._court_fields_of_finding                (fixed 11-key)
      -> matrix_policy._merge_group / _court_fields_of        (COURT_ROW_FIELDS)
      -> worker._matrix_rows_for_summary                      (_SUMMARY_MATRIX_ROW_KEYS)
      -> worker._state_summary findings                       (hard-coded 8-key)

#262 threads the three fields through all of them so they survive to the UI.
Structured dicts are kept as dicts, never stringified; a non-dict value coerces
to {} so one malformed field can't poison a row/summary. Capture-only: no
severity/confidence/ADR-004 gate changes.

Prediction (before running): the three fields arrive verbatim in the merged
matrix row, the summary matrix_rows, and the summary findings; a garbage value
becomes {} everywhere; an absent field becomes ""/{}.

Offline: pure functions, no workspace/LLM/git.
"""
from agent.matrix_policy import merge_contract_results
from agent.worker import _matrix_rows_for_summary, _state_summary

_DB_VIOLATION = {
    "marker": "DB STATE VIOLATION",
    "head_observed": True,
    "base_observed": False,
    "head_only": True,
}
_BEHAVIORAL = {
    "captured": True,
    "head_test_failed": True,
    "db_effect_rolled_back": False,
    "failing_method": "changeEmail",
    "note": "Behavioral regression with captured DB mutation.",
}
_DB_DETAIL = "Head persisted a duplicate email; base did not."


def _court_entry(**overrides: object) -> dict:
    row = {
        "contract_id": "AUTH-01",
        "severity": "BLOCKER",
        "confidence": 0.95,
        "evidence_type": "base_pass_head_fail",
        "verdict": "REGRESSION",
        "detail": "duplicate email persisted",
        "status": "confirmed",
        "source": "differential",
        "type": "differential_regression",
        "location": "src/AuthController.java",
        "evidence_digest": "",
        "finding_id": "COURT-AUTH-01",
        "db_state_detail": _DB_DETAIL,
        "db_violation_evidence": dict(_DB_VIOLATION),
        "behavioral_evidence": dict(_BEHAVIORAL),
    }
    row.update(overrides)
    return row


def _finding(**overrides: object) -> dict:
    f = {
        "id": "COURT-AUTH-01",
        "contract_id": "AUTH-01",
        "severity": "BLOCKER",
        "confidence": 0.95,
        "evidence_type": "base_pass_head_fail",
        "type": "differential_regression",
        "location": "src/AuthController.java",
        "description": "duplicate email accepted and persisted",
        "db_state_detail": _DB_DETAIL,
        "db_violation_evidence": dict(_DB_VIOLATION),
        "behavioral_evidence": dict(_BEHAVIORAL),
    }
    f.update(overrides)
    return f


class TestMergedMatrixRowCarriesEvidence:
    def test_row_carries_evidence_dicts_verbatim(self) -> None:
        row = merge_contract_results([_court_entry()])[0]
        assert row["db_state_detail"] == _DB_DETAIL
        assert row["db_violation_evidence"] == _DB_VIOLATION
        assert row["behavioral_evidence"] == _BEHAVIORAL

    def test_non_dict_evidence_coerces_to_empty(self) -> None:
        row = merge_contract_results([
            _court_entry(db_violation_evidence="garbage", behavioral_evidence=None)
        ])[0]
        assert row["db_violation_evidence"] == {}
        assert row["behavioral_evidence"] == {}

    def test_absent_evidence_defaults_empty(self) -> None:
        entry = _court_entry()
        del entry["db_violation_evidence"]
        del entry["behavioral_evidence"]
        del entry["db_state_detail"]
        row = merge_contract_results([entry])[0]
        assert row["db_violation_evidence"] == {}
        assert row["behavioral_evidence"] == {}
        assert row["db_state_detail"] == ""


class TestSummaryMatrixRowsCarryEvidence:
    def test_matrix_rows_projection_keeps_evidence(self) -> None:
        out = _matrix_rows_for_summary({"rows": [_court_entry()]})
        assert out["matrix_rows"]
        row = out["matrix_rows"][0]
        assert row["db_state_detail"] == _DB_DETAIL
        assert row["db_violation_evidence"] == _DB_VIOLATION
        assert row["behavioral_evidence"] == _BEHAVIORAL


class TestStateSummaryFindingsCarryEvidence:
    def test_summary_findings_carry_evidence(self) -> None:
        state = {"matrix": {}, "contracts": [], "confirmed_findings": [_finding()], "errors": []}
        f = _state_summary(state, "BLOCKED")["findings"][0]
        assert f["db_state_detail"] == _DB_DETAIL
        assert f["db_violation_evidence"] == _DB_VIOLATION
        assert f["behavioral_evidence"] == _BEHAVIORAL

    def test_non_dict_evidence_coerced_in_summary(self) -> None:
        finding = _finding(db_violation_evidence="garbage", behavioral_evidence=None)
        state = {"matrix": {}, "contracts": [], "confirmed_findings": [finding], "errors": []}
        f = _state_summary(state, "BLOCKED")["findings"][0]
        assert f["db_violation_evidence"] == {}
        assert f["behavioral_evidence"] == {}
