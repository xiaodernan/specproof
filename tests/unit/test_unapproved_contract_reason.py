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

    def test_the_generic_reason_is_used_when_there_is_no_specific_one(
        self,
    ) -> None:
        """A row with no reason of its own still gets the generic one."""
        decision = evaluate_verification({
            "rows": [{"contract_id": "C-1", "result": "UNVERIFIED"}],
        })
        assert decision.status == "NEEDS_REVIEW"
        assert "尚未得到可判定结果" in decision.reason


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
        assert "尚未得到可判定结果" in decision.reason

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

    def test_an_unknown_code_falls_back_to_the_generic_sentence(self) -> None:
        """A code nobody declared must not invent a sentence."""
        decision = evaluate_verification({
            "rows": [{
                "contract_id": "C-1",
                "result": "UNVERIFIED",
                "unverified_reason_code": "something_a_node_made_up",
            }],
        })
        assert decision.status == "NEEDS_REVIEW"
        assert "尚未得到可判定结果" in decision.reason


class TestTheJobDoesNotParkOnContractReview:
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
