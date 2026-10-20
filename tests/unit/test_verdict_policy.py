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
    decision = evaluate_verification(matrix)
    # The invariant this file exists for: an unjudgeable row must never
    # ACCEPT the change. The WORD depends on whether anything is proven
    # wrong: a contract that FAILED is BLOCKED (fix the code), an
    # incomplete row is not (a human has to look) — so the word is
    # asserted, not just "not VERIFIED".
    expected = "BLOCKED" if changes.get("result") == "FAIL" else "NEEDS_REVIEW"
    assert decision.status == expected
    assert decision.status != "VERIFIED"
    assert _terminal_status_from_state(state) == expected
    assert _verification_summary(state)["verdict"] == expected
    html = render_verification_report("r", "b", "h", matrix, [])
    assert '<div class="verdict verified">' not in html
    assert _state_summary(state, expected)["coverage_reason"]


@pytest.mark.parametrize("matrix,expected", [
    # No checks at all: nothing was measured, so nothing is proven wrong.
    ({"rows": []}, "NEEDS_REVIEW"),
    ({"rows": None}, "NEEDS_REVIEW"),
    # A row that is not even a mapping: the run produced garbage.
    ({"rows": [None]}, "BLOCKED"),
    # The summary claims one failure; no row is one. The two records
    # contradict each other — a reader cannot tell which is the truth.
    ({"rows": [passing_row()], "failed": 1}, "BLOCKED"),
    ({"rows": [passing_row()], "passed": 0}, "BLOCKED"),
    ({"rows": [passing_row()], "passed": True}, "BLOCKED"),
    ({"rows": [passing_row()], "unverified": "0"}, "BLOCKED"),
    ({"rows": [passing_row()], "total_rows": 2}, "BLOCKED"),
    ({"rows": [passing_row()], "total_contracts": 2}, "BLOCKED"),
    ({"rows": [passing_row()], "total_contracts": 0}, "BLOCKED"),
    # Two rows for one contract: they disagree, and a reader cannot pick
    # one — the evidence contradicts itself.
    ({"rows": [passing_row(), passing_row()]}, "BLOCKED"),
    ({"rows": [passing_row(), passing_row() | {"result": "FAIL"}]}, "BLOCKED"),
    # A row for a contract that does not exist is a contradiction; a
    # contract with no row is a coverage gap. Here only the gap is
    # present, so the word is NEEDS_REVIEW.
    ({"rows": [passing_row()], "contract_ids": ["C-1", "C-2"]}, "NEEDS_REVIEW"),
])
def test_contradictory_or_incomplete_matrices_say_which_one_they_are(matrix, expected):
    """The reason table decides the word, and this pins it row by row.

    A matrix that contradicts itself is BLOCKED (something is wrong, or
    the two records disagree); a matrix that merely lacks evidence is
    NEEDS_REVIEW (nothing is proven either way). Both are fail-closed;
    they differ in what the reader is sent to do.
    """
    decision = evaluate_verification(matrix)
    assert decision.status == expected
    assert decision.status != "VERIFIED"
    if expected == "BLOCKED":
        assert decision.blocking, decision.reasons
    else:
        assert not decision.blocking, decision.reasons


def test_the_two_middle_verdicts_say_different_things():
    """BLOCKED and NEEDS_REVIEW are both fail-closed, and they differ.

    A contract that FAILED is a real problem: the change is wrong, and
    the answer is "fix it and re-verify". A contract with no decidable
    result proves nothing either way: the answer is "a human has to
    look". Sending both to the same reader is how a reader learns to
    ignore the word.
    """
    failed = evaluate_verification({"rows": [passing_row() | {"result": "FAIL"}]})
    unjudged = evaluate_verification({"rows": [passing_row() | {"evidence": ""}]})

    assert failed.status == "BLOCKED"
    assert unjudged.status == "NEEDS_REVIEW"
    # The decision says WHICH of its reasons are the blocking ones, so a
    # consumer can tell "the bytes differ" from "the bytes are missing".
    assert failed.blocking
    assert not unjudged.blocking
    assert set(failed.blocking) <= set(failed.reasons)


def test_a_refused_release_gate_is_a_blocking_reason():
    """A gate that REFUSED is a real problem; one that could not be
    judged is an evidence gap. The decision says which."""
    from evidence.verdict import evaluate_acceptance

    refused = evaluate_acceptance(
        {"rows": [passing_row()]},
        contracts=[{"id": "C-1"}],
        release={
            "passed": False,
            "gates": {"reproducibility": {"passed": False}},
        },
    )
    unjudged = evaluate_acceptance(
        {"rows": [passing_row()]},
        contracts=[{"id": "C-1"}],
        release={
            "passed": False,
            "gates": {"reproducibility": {"first_head_pass": False}},
        },
    )

    assert refused.status == "BLOCKED"
    assert refused.blocking, "a refused gate is a real problem"
    assert unjudged.status == "NEEDS_REVIEW"
    assert not unjudged.blocking, "an unjudged gate is an evidence gap"


def test_coverage_compares_ids_not_only_counts():
    decision = evaluate_verification(
        {"rows": [passing_row("C-1"), passing_row("OTHER")]},
        contracts=[{"id": "C-1"}, {"id": "C-2"}],
    )
    # Two gaps here: C-2 has no row (a coverage gap), and OTHER is a row
    # for a contract that does not exist (a self-contradiction). The
    # contradiction decides the word.
    assert decision.status == "BLOCKED"
    assert "C-2" in decision.reason
    assert decision.unverified == 1


def test_a_missing_contract_alone_is_a_coverage_gap():
    """No row for a contract, and nothing that contradicts anything.

    This is the shape a reader must be able to recognise as "the
    evidence is missing", not "the change is bad".
    """
    decision = evaluate_verification(
        {"rows": [passing_row("C-1")]},
        contracts=[{"id": "C-1"}, {"id": "C-2"}],
    )
    assert decision.status == "NEEDS_REVIEW"
    assert "C-2" in decision.reason
    assert decision.unverified == 1
    assert not decision.blocking


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



def test_certificate_issuance_is_observable():
    """§8.10 "Certificate 签发率" (#179): the VERIFIED exit counts an issue,
    the non-VERIFIED exit counts a refusal — the issuance ratio is
    derivable from rates, and neither exit is silent."""
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()["counters"]
    ok = issue_certificate("r", "s", "req", [passing_row(), passing_row("C-2")])
    refused = issue_certificate(
        "r", "s", "req", [passing_row("C-3") | {"result": "FAIL"}]
    )
    after = metrics_module.snapshot()["counters"]

    assert ok is not None and refused is None
    issued = after["certificates_issued_total"] - before.get(
        "certificates_issued_total", 0.0
    )
    refusals = after["certificates_refused_total"] - before.get(
        "certificates_refused_total", 0.0
    )
    assert issued == 1
    assert refusals == 1


def test_rejection_notice_counts_when_written():
    """build_rejection_notice counts an actually written notice — a
    different fact from the refusal decision itself (a caller may decline
    to write one)."""
    from evidence.certificate import build_rejection_notice
    from observability import metrics as metrics_module

    before = metrics_module.snapshot()["counters"].get(
        "rejection_notices_total", 0.0
    )
    build_rejection_notice(
        "r", "s", "req", [passing_row("C-4") | {"result": "FAIL"}],
        ["no evidence"],
    )
    after = metrics_module.snapshot()["counters"].get(
        "rejection_notices_total", 0.0
    )
    assert after - before == 1
