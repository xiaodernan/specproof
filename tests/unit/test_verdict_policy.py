"""Acceptance counterexamples shared by worker, HTML, CLI and certificate paths."""
from copy import deepcopy

import pytest

from agent.contract_results import merge_contract_results
from agent.worker import _state_summary, _terminal_status_from_state
from craft.accept import _verification_summary
from evidence.certificate import issue_certificate
from evidence.report import render_verification_report
from evidence.verdict import contracts_with_results, evaluate_verification


def passing_row(cid="C-1"):
    return {"contract_id": cid, "result": "PASS", "experiment": "STATIC-01", "evidence": "ev-1"}


@pytest.mark.parametrize("changes", [
    {"evidence": ""}, {"evidence": "—"}, {"evidence": "none"}, {"evidence": " N/A "},
    {"evidence": []}, {"evidence": {"fake": "ref"}},
    {"experiment": "none"}, {"experiment": ""}, {"contract_id": ""},
    {"result": "FAIL"}, {"result": "UNVERIFIED"}, {"result": "UNKNOWN"},
])
def test_incomplete_rows_never_verify_across_consumers(changes):
    row = passing_row() | changes
    matrix = {"rows": [row]}
    state = {"matrix": matrix, "contracts": [{"id": "C-1"}]}
    assert evaluate_verification(matrix).status == "BLOCKED"
    assert _terminal_status_from_state(state) == "BLOCKED"
    assert _verification_summary(state)["verdict"] == "BLOCKED"
    html = render_verification_report("r", "b", "h", matrix, [])
    assert '<div class="verdict verified">' not in html
    assert _state_summary(state, "BLOCKED")["coverage_reason"]


@pytest.mark.parametrize("matrix", [
    {"rows": []}, {"rows": None}, {"rows": [None]},
    {"rows": [passing_row()], "failed": 1},
    {"rows": [passing_row()], "passed": 0},
    {"rows": [passing_row()], "passed": True},
    {"rows": [passing_row()], "unverified": "0"},
    {"rows": [passing_row()], "total_rows": 2},
    {"rows": [passing_row()], "total_contracts": 2},
    {"rows": [passing_row()], "total_contracts": 0},
    {"rows": [passing_row(), passing_row()]},
    {"rows": [passing_row(), passing_row() | {"result": "FAIL"}]},
    {"rows": [passing_row()], "contract_ids": ["C-1", "C-2"]},
])
def test_contradictory_or_incomplete_matrices_are_blocked(matrix):
    assert evaluate_verification(matrix).status == "BLOCKED"


def test_coverage_compares_ids_not_only_counts():
    decision = evaluate_verification(
        {"rows": [passing_row("C-1"), passing_row("OTHER")]},
        contracts=[{"id": "C-1"}, {"id": "C-2"}],
    )
    assert decision.status == "BLOCKED"
    assert "C-2" in decision.reason
    assert decision.unverified == 1


def test_matrix_downgrades_unsupported_pass_before_consumers_render_it():
    from agent.nodes.build_matrix import build_matrix_node

    matrix = build_matrix_node({
        "contracts": [{"id": "C-1"}],
        "contract_results": [{"contract_id": "C-1", "result": "PASS", "experiment": "e1"}],
    })["matrix"]
    assert matrix["rows"][0]["result"] == "UNVERIFIED"
    assert "缺少证据" in matrix["rows"][0]["unverified_reason"]
    assert matrix["passed"] == 0
    assert matrix["unverified"] == 1


def test_valid_current_and_legacy_evidence_verify_without_mutation():
    matrix = {"rows": [passing_row(), {
        "contract_id": "C-2", "result": "PASS", "experiment_ids": ["DIFF-01"],
        "evidence_refs": ["sha256:" + "a" * 64],
    }], "total_contracts": 2, "passed": 2, "failed": 0, "unverified": 0, "total_rows": 2}
    before = deepcopy(matrix)
    decision = evaluate_verification(matrix, contracts=[{"id": "C-1"}, {"id": "C-2"}])
    assert decision.status == "VERIFIED"
    assert decision.passed == 2
    assert matrix == before
    html = render_verification_report("r", "b", "h", matrix, [])
    assert '<div class="verdict verified">VERIFIED</div>' in html


def test_error_precedes_pass_and_findings():
    assert evaluate_verification({"rows": [passing_row()]}, errors=["timeout"]).status == "FAILED"
    assert evaluate_verification({"rows": [passing_row()]}, findings=[{}]).status == "BLOCKED"


@pytest.mark.parametrize("contracts", [
    [], [{"id": "C-1", "result": "PASS"}],
    [{"id": "C-1", "result": "PASS", "evidence_ref": "—"}],
    [{"result": "PASS", "evidence_ref": "e1"}],
    [passing_row(), passing_row()],
    [passing_row(), passing_row("C-2") | {"result": "FAIL"}],
])
def test_certificate_requires_individual_contract_evidence(contracts):
    assert issue_certificate("r", "h", "spec", contracts, evidence_digests=["unrelated"]) is None


def test_certificate_includes_evidence_from_each_contract():
    certificate = issue_certificate("r", "h", "spec", [passing_row()])
    assert certificate is not None
    assert certificate.verified_contracts == 1
    assert certificate.evidence_digests == ["ev-1"]


def test_failure_survives_duplicate_existing_channel_and_certificate_merge():
    records = [
        {"contract_id": "C-1", "result": "FAIL", "evidence_ref": "failure"},
        {"contract_id": "C-1", "result": "PASS", "evidence_ref": "pass"},
    ]
    assert merge_contract_results(records, [])[0]["result"] == "FAIL"
    merged = contracts_with_results([{"id": "C-1"}], records)
    assert merged[0]["result"] == "FAIL"
    assert issue_certificate("r", "h", "spec", merged) is None


def test_static_results_keep_existing_evidence_when_workspaces_absent():
    from agent.nodes.run_static_checks import run_static_checks_node

    recorded = [{"contract_id": "C-1", "result": "FAIL", "evidence_ref": "real-failure"}]
    assert run_static_checks_node({"contract_results": recorded})["contract_results"] == recorded


def test_static_pass_references_exact_inputs_and_deleted_class_is_unverified(tmp_path):
    from agent.nodes.run_static_checks import run_static_checks_node

    base, head = tmp_path / "base", tmp_path / "head"
    rel = "src/main/java/AccountService.java"
    source = "public class AccountService { @Transactional public void save() { work(); } }"
    for root in (base, head):
        (root / rel).parent.mkdir(parents=True)
        (root / rel).write_text(source, encoding="utf-8")
    state = {"base_workspace": str(base), "head_workspace": str(head),
             "contracts": [{"id": "TRANSACTION-01"}]}
    original = run_static_checks_node(state)["contract_results"][0]
    assert original["result"] == "PASS"
    assert original["evidence_ref"].startswith("static:TRANSACTION-01:")
    assert run_static_checks_node(state)["contract_results"][0] == original
    (head / rel).write_text(source.replace("work();", "work(); other();"), encoding="utf-8")
    changed = run_static_checks_node(state)["contract_results"][0]
    assert changed["evidence_ref"] != original["evidence_ref"]
    (head / rel).unlink()
    deleted = run_static_checks_node(state)["contract_results"][0]
    assert deleted["result"] == "UNVERIFIED"
    assert "被删除" in deleted["details"]
