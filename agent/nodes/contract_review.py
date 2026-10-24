"""contract_review node — honest production writer for CONTRACT_REVIEW status.

The frozen state machine (storage/mysql.py) has a CONTRACT_REVIEW state that
was reachable but never written by any pipeline node. This node is the
production writer: when the contract compilation finishes and there are
unapproved contracts, the pipeline REALLY STOPS here and waits for human
approval.

If all contracts are approved (implicit or explicit), the node is a no-op
and the pipeline proceeds to PREPARING/RUNNING without ever writing
CONTRACT_REVIEW — because nobody is actually waiting for approval.

The node emits a graph event "contract_review" that job_stage.py maps to
the CONTRACT_REVIEW status, and the worker's advance_for_stage writes it.
"""

from __future__ import annotations

from typing import Any

from agent.state import Phase0State
from observability.metrics import incr


def _has_unapproved_contracts(contracts: list[dict[str, Any]]) -> bool:
    """Return True if any contract lacks approval (explicit or implicit)."""
    return any(not c.get("approved", False) for c in contracts)


def _unapproved_summary(contracts: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build a summary of unapproved contracts for the event payload."""
    out = []
    for c in contracts:
        if not c.get("approved", False):
            out.append({
                "id": str(c.get("id", "?")),
                "checker_type": str(c.get("checker_type", "?")),
                "requirement": str(c.get("requirement", ""))[:120],
            })
    return out


def contract_review_node(state: Phase0State) -> dict[str, Any]:
    """Check contract approvals; if any are unapproved, STOP and wait.

    This is the HONEST production writer for CONTRACT_REVIEW:
    - If there are unapproved contracts: record the fact, emit the stage,
      and the worker will write CONTRACT_REVIEW to the job row. The
      pipeline does NOT proceed past this node until an external signal
      (human approval via API) marks the contracts approved and resumes.
    - If all contracts are approved: do nothing (no status write), let the
      pipeline continue through PREPARING → RUNNING naturally.

    The stage name "contract_review" is registered in agent/job_stage.py
    STAGE_STATUS mapping, so advance_for_stage will write CONTRACT_REVIEW
    when this stage finishes.

    Returns a dict with:
    - "contract_review": dict containing the review outcome
    - "errors": updated error list (if any)
    - "stage": "contract_review" (for job_stage advancement)
    """
    contracts = state.get("contracts", [])
    errors: list[str] = list(state.get("errors", []))

    if not contracts:
        # No contracts compiled — nothing to approve. This is honest:
        # the pipeline will proceed and the Review Court will report
        # UNVERIFIED for the empty matrix. We do NOT write CONTRACT_REVIEW
        # because there is nobody waiting for anything.
        incr("contract_review_runs_total")
        incr("contract_review_outcomes_no_contracts_total")
        return {
            "contract_review": {
                "status": "no_contracts",
                "message": "No contracts compiled; nothing to approve",
                "unapproved": [],
            },
            "errors": errors,
            "stage": "contract_review",
        }

    if _has_unapproved_contracts(contracts):
        # THERE ARE UNAPPROVED CONTRACTS — the pipeline MUST STOP HERE.
        # The worker will write CONTRACT_REVIEW to the job row.
        # An external API call (POST /api/v1/jobs/{id}/approve-contracts)
        # must mark the contracts approved and resume the graph.
        unapproved = _unapproved_summary(contracts)
        incr("contract_review_runs_total")
        incr("contract_review_outcomes_waiting_total")
        return {
            "contract_review": {
                "status": "waiting_for_approval",
                "message": f"{len(unapproved)} contract(s) require human approval",
                "unapproved": unapproved,
            },
            "errors": errors,
            "stage": "contract_review",
            # Signal to the graph executor that we should pause here.
            # The actual pause is implemented by the worker checking
            # state["contract_review"]["status"] == "waiting_for_approval"
            # and not invoking the next node until resumed.
            "paused": True,
        }

    # All contracts are approved — no wait needed. We do NOT write
    # CONTRACT_REVIEW because nobody is actually waiting.
    incr("contract_review_runs_total")
    incr("contract_review_outcomes_all_approved_total")
    return {
        "contract_review": {
            "status": "all_approved",
            "message": "All contracts approved (implicit or explicit); proceeding",
            "unapproved": [],
        },
        "errors": errors,
        "stage": "contract_review",
    }


__all__ = ["contract_review_node", "_has_unapproved_contracts", "_unapproved_summary"]
