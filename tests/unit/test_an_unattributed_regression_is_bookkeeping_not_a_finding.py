"""An UNATTRIBUTED regression is bookkeeping, not a finding.

WHY. "Base passed, Head failed" is the SHAPE of a regression. Whether the
failure names the code this change touched is the QUESTION that separates
"the change broke it" from "the generated test's own expectation was
wrong" — measured on the real model, it was the one false positive in six
negative cases (ledger #1638): a PR that merely ADDED an endpoint got a
test asserting an unauthenticated request is rejected, it failed on Head,
and the review court reported a MAJOR regression.

The rule the tool now follows is the one it already followed for a failing
test that did not exercise the contract: severity NONE means bookkeeping,
not a finding. The tool saw something fail on Head; it cannot say it is
about this change, so it must not claim a defect WITH A LEVEL. The entry
keeps the whole story (exit codes, outputs, the attribution) so a reader
can judge it themselves.

WHAT THIS DOES NOT CLAIM. It does not prove the tool finds fewer real
regressions: a real regression's failing test names the changed code, so
it stays attributed. What it proves is that a failure the tool cannot
attribute no longer arrives as a defect claim.
"""

from __future__ import annotations

from typing import Any

from agent.nodes.run_differential import _apply_attribution

CHANGED = ["src/main/java/com/specproof/demo/controller/UserController.java"]


def _entry(head_output: str) -> dict[str, Any]:
    return {
        "contract_id": "AUTH-01",
        "verdict": "REGRESSION",
        "severity": "MAJOR",
        "detail": "Test passes in Base (exit 0) but fails in Head (exit 1).",
        "head_output": head_output,
    }


def test_a_failure_that_names_the_changed_code_stays_a_finding() -> None:
    entry = _entry(
        "stack=at com.specproof.demo.controller.UserController.changeEmail("
        "UserController.java:42)"
    )
    _apply_attribution(entry, CHANGED)
    assert entry["attribution"] == "changed_code_in_failure"
    assert entry["severity"] == "MAJOR", (
        "an attributed regression keeps its level — the policy only demotes "
        "what it cannot attribute"
    )


def test_a_failure_that_names_nothing_changed_becomes_bookkeeping() -> None:
    entry = _entry(
        "stack=at com.specproof.demo.controller.ProductController.get("
        "ProductController.java:31)"
    )
    _apply_attribution(entry, CHANGED)
    assert entry["attribution"] == "changed_code_not_in_failure"
    assert entry["severity"] == "NONE", (
        "a failure the tool cannot attribute must not arrive as a defect "
        "claim (#1638)"
    )
    assert "UNATTRIBUTED" in entry["detail"], entry["detail"]


def test_unknown_attribution_demotes_nothing() -> None:
    """No output to read, or no changed paths: the tool knows nothing, and
    it does not turn "I know nothing" into "it is fine"."""
    entry = _entry("")
    _apply_attribution(entry, CHANGED)
    assert entry["attribution"] == "unknown"
    assert entry["severity"] == "MAJOR", (
        "unknown is not unattributed: the tool must not demote a regression "
        "merely because it could not read the output"
    )
