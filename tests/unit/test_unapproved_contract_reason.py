"""A row that was never approved must say so (Phase 3, #308).

The Review Court's first BLOCKER condition is "the contract is
approved" — an unapproved contract cannot back an acceptance. But the
matrix row for such a contract used to read a bare ``UNVERIFIED`` with
**no reason at all**, and the verdict said "尚未得到可判定结果" (no
decidable result).

Both sentences point the reader at the wrong next action. The reader is
told to go looking for missing evidence, when the truth is: nobody
approved this contract. That is a different task with a different
owner — and the row is the only place that can say it, because the
matrix builder is the one that holds the approval flag.

This file pins that the reason travels all the way to the verdict's
prose, which is what a human actually reads.
"""

from __future__ import annotations

from typing import Any

from agent.nodes.build_matrix import UNAPPROVED_CONTRACT_REASON, build_matrix_node
from evidence.verdict import evaluate_verification


def _state(approved: bool) -> dict[str, Any]:
    return {
        "contracts": [
            {
                "id": "AUTH-01",
                "requirement": "未认证请求必须 401",
                "checker_type": "http",
                "version": 1,
                "approved": approved,
                "result": "UNVERIFIED",
            },
        ],
        "contract_results": [],
        "diff_results": [],
        "findings": [],
    }


class TestTheRowSaysWhy:
    def test_an_unapproved_contract_row_names_the_approval(self) -> None:
        matrix = build_matrix_node(_state(approved=False))["matrix"]
        row = matrix["rows"][0]
        assert row["result"] == "UNVERIFIED"
        assert row["unverified_reason"] == UNAPPROVED_CONTRACT_REASON
        assert "未获批准" in row["unverified_reason"]

    def test_an_approved_contract_row_carries_no_approval_reason(self) -> None:
        """The reason must not appear when it is not true.

        A row that says "the contract was never approved" when it WAS
        approved sends the reader to approve a contract that is already
        approved — a wrong next action is worse than no next action.
        """
        matrix = build_matrix_node(_state(approved=True))["matrix"]
        row = matrix["rows"][0]
        assert "未获批准" not in str(row.get("unverified_reason") or "")


class TestTheVerdictCarriesIt:
    def test_the_verdict_reasons_name_the_approval_gap(self) -> None:
        matrix = build_matrix_node(_state(approved=False))["matrix"]
        decision = evaluate_verification(matrix)
        assert decision.status == "NEEDS_REVIEW"
        assert "未获批准" in decision.reason
        # It is a GAP, not a contradiction: nothing is proven wrong, the
        # evidence simply cannot be trusted until a human approves.
        assert not decision.blocking

    def test_a_row_with_no_label_still_gets_a_derived_reason(self) -> None:
        """The verdict derives the reason; a missing label is not a blank.

        The row's experiment record says whether an experiment ran, so
        the verdict can name the reason without the node's help.
        """
        decision = evaluate_verification({
            "rows": [{"contract_id": "C-1", "result": "UNVERIFIED"}],
        })
        assert decision.status == "NEEDS_REVIEW"
        assert "没有任何实验产出结果" in decision.reason

    def test_a_row_that_ran_an_experiment_says_so(self) -> None:
        decision = evaluate_verification({
            "rows": [{
                "contract_id": "C-1",
                "result": "UNVERIFIED",
                "experiment_ids": ["STATIC-01"],
            }],
        })
        assert decision.status == "NEEDS_REVIEW"
        assert "实验已运行但未得到可判定证据" in decision.reason


class TestTheOutwardReasonIsAControlledVocabulary:
    """A node's free prose must not become the product's conclusion.

    A matrix row may carry whatever prose its node wrote ("Maven
    execution error: …") — the row-level view shows it, and it is more
    informative than any summary. But the verdict's ``reason`` is QUOTED
    OUTWARD (the HTML report, the CLI output, the notification body), and
    letting a node choose the product's outward wording is not something
    the verdict layer should hand out.
    """

    def test_a_rows_free_prose_is_not_quoted_by_the_verdict(self) -> None:
        decision = evaluate_verification({
            "rows": [{
                "contract_id": "C-1",
                "result": "UNVERIFIED",
                "unverified_reason": "Maven execution error: exit code 1",
            }],
        })
        assert decision.status == "NEEDS_REVIEW"
        assert "Maven execution error" not in decision.reason
        # The verdict's own sentence, derived from the row's experiment
        # record — not the node's prose, and not a blank.
        assert "没有任何实验产出结果" in decision.reason

    def test_a_controlled_code_is_quoted(self) -> None:
        """The code is how a row says WHICH controlled sentence applies."""
        from evidence.verdict import ROW_REASON_CONTRACT_NOT_APPROVED

        decision = evaluate_verification({
            "rows": [{
                "contract_id": "C-1",
                "result": "UNVERIFIED",
                "unverified_reason_code": ROW_REASON_CONTRACT_NOT_APPROVED,
            }],
        })
        assert decision.status == "NEEDS_REVIEW"
        assert "未获批准" in decision.reason

    def test_an_unknown_code_falls_back_to_a_derived_sentence(self) -> None:
        """A code nobody declared must not invent a sentence."""
        decision = evaluate_verification({
            "rows": [{
                "contract_id": "C-1",
                "result": "UNVERIFIED",
                "unverified_reason_code": "something_a_node_made_up",
            }],
        })
        assert decision.status == "NEEDS_REVIEW"
        assert "something_a_node_made_up" not in decision.reason
        assert "没有任何实验产出结果" in decision.reason


class TestTheVerdictDerivesWhatItCanCompute:
    """A node's LABEL is a hint; the verdict layer computes what it can.

    The verdict layer holds the contracts, and a contract's approval
    flag is a fact it can read for itself. If it trusted the row's
    label instead, a node that mislabelled an unapproved contract as
    "no experiment" would make the product say the wrong thing about
    its own conclusion — and the reader would go looking for evidence
    that is not the missing piece.
    """

    def test_a_mislabelled_row_cannot_hide_the_approval_gap(self) -> None:
        from evidence.verdict import ROW_REASON_NO_EXPERIMENT

        decision = evaluate_verification(
            {"rows": [{
                "contract_id": "C-1",
                "result": "UNVERIFIED",
                # The node says "no experiment ran" …
                "unverified_reason_code": ROW_REASON_NO_EXPERIMENT,
            }]},
            contracts=[{"id": "C-1", "approved": False}],
        )
        # … but the contract says it was never approved, and that is what
        # the reader is told.
        assert decision.status == "NEEDS_REVIEW"
        assert "未获批准" in decision.reason
        assert "没有任何实验产出结果" not in decision.reason

    def test_an_approved_contract_keeps_the_nodes_own_label(self) -> None:
        """The derivation only OVERRIDES the label when the fact says so."""
        from evidence.verdict import ROW_REASON_NO_EXPERIMENT

        decision = evaluate_verification(
            {"rows": [{
                "contract_id": "C-1",
                "result": "UNVERIFIED",
                "unverified_reason_code": ROW_REASON_NO_EXPERIMENT,
            }]},
            contracts=[{"id": "C-1", "approved": True}],
        )
        assert decision.status == "NEEDS_REVIEW"
        assert "没有任何实验产出结果" in decision.reason

    def test_without_the_contracts_the_label_is_all_there_is(self) -> None:
        """The certificate path has no contract list — the label still works."""
        from evidence.verdict import ROW_REASON_NO_EXPERIMENT

        decision = evaluate_verification({
            "rows": [{
                "contract_id": "C-1",
                "result": "UNVERIFIED",
                "unverified_reason_code": ROW_REASON_NO_EXPERIMENT,
            }],
        })
        assert "没有任何实验产出结果" in decision.reason


class TestTheRowNeverContradictsTheFacts:
    """A row's code must agree with the facts the row-level view shows.

    The verdict layer OVERRIDES a wrong label (#310), so a mislabelled
    row would still produce a correct outward conclusion — and the row
    itself would still DISPLAY the wrong reason. Silence is not a
    gate: this checks the row against the facts it was built from, so a
    future change that lets a row claim "never approved" for an
    approved contract goes red HERE rather than being quietly corrected
    somewhere downstream.
    """

    def _matrix(self, approvals: dict[str, bool]) -> dict[str, Any]:
        contracts = [
            {
                "id": cid,
                "requirement": f"要求 {cid}",
                "checker_type": "http",
                "version": 1,
                "approved": approved,
                "result": "UNVERIFIED",
            }
            for cid, approved in approvals.items()
        ]
        return build_matrix_node({
            "contracts": contracts,
            "contract_results": [],
            "diff_results": [],
            "findings": [],
        })["matrix"]

    def test_the_approval_code_agrees_with_the_approval_fact(self) -> None:
        from evidence.verdict import ROW_REASON_CONTRACT_NOT_APPROVED

        matrix = self._matrix({"A-1": True, "B-1": False, "C-1": True})
        approvals = {"A-1": True, "B-1": False, "C-1": True}
        for row in matrix["rows"]:
            cid = row["contract_id"]
            code = str(row.get("unverified_reason_code") or "")
            if approvals[cid]:
                assert code != ROW_REASON_CONTRACT_NOT_APPROVED, (
                    f"{cid} is approved, so its row must not claim it was not"
                )
            else:
                assert code == ROW_REASON_CONTRACT_NOT_APPROVED, (
                    f"{cid} was never approved, so its row must say so"
                )

    def test_the_row_and_the_verdict_agree_on_the_approval_fact(self) -> None:
        """The row-level view and the outward conclusion must not differ."""
        from evidence.verdict import ROW_REASON_CONTRACT_NOT_APPROVED

        matrix = self._matrix({"A-1": True, "B-1": False})
        decision = evaluate_verification(
            matrix, contracts=[
                {"id": "A-1", "approved": True},
                {"id": "B-1", "approved": False},
            ],
        )
        unapproved_rows = [
            row for row in matrix["rows"]
            if row.get("unverified_reason_code") == ROW_REASON_CONTRACT_NOT_APPROVED
        ]
        assert [row["contract_id"] for row in unapproved_rows] == ["B-1"]
        assert "未获批准" in decision.reason
        # The approved contract's row does NOT claim otherwise, so the
        # outward reason mentions only the one that is really unapproved.
        assert decision.reason.count("未获批准") == 1
    """Why there is no CONTRACT_REVIEW producer — pinned as behaviour.

    The frozen state machine has a CONTRACT_REVIEW status, and the
    obvious way to use it would be "the job is waiting for a human to
    approve the contracts". But the pipeline does NOT wait: it runs the
    experiments with the unapproved contracts and lets the Review Court
    refuse to certify on them (its condition 1). The job therefore ends,
    and it ends in NEEDS_REVIEW — "a human has to look" — rather than
    sitting in a status that claims it is parked.

    Writing CONTRACT_REVIEW here would be the pipeline telling a reader
    "someone is working on your approval" when nobody is. So it is not
    written, and this test says so out loud.
    """

    def test_the_verdict_is_needs_review_not_a_waiting_state(self) -> None:
        from storage.mysql import _VALID_TRANSITIONS

        matrix = build_matrix_node(_state(approved=False))["matrix"]
        decision = evaluate_verification(matrix)
        # The job's terminal status comes from the verdict, and the verdict
        # is NEEDS_REVIEW. CONTRACT_REVIEW is reachable in the machine …
        assert "CONTRACT_REVIEW" in _VALID_TRANSITIONS["PREPARING"]
        # … but no producer writes it, because the pipeline never waits.
        assert decision.status == "NEEDS_REVIEW"
        assert decision.status != "CONTRACT_REVIEW"
