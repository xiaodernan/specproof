"""The deterministic template must follow the CONTRACTS, not a fixed story.

WHY. The deterministic template used to be the base of EVERY generated
test: unauthenticated PUT -> 401 AND the DB row unchanged. That is the
right test for a change that removed a guard — and the wrong test for a
change that did not. Measured on the real model (ledger #1638): a PR that
merely ADDED a product-detail endpoint got that test, it failed on Head,
and the review court reported a MAJOR regression. The tool asserted a
defect it had no evidence for.

So a change whose contracts name no family this tier can execute now
produces NO test at all — and the case is honestly UNJUDGEABLE ("no
generated test") rather than falsely red. The difference between "we
looked and found nothing" and "we did not look" is the whole point.

These legs pin that shape: the AUTH template belongs to the AUTH family,
the other families keep their own, and a change with no matching family
produces no test and says why.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import agent.nodes.generate_counterexamples as gen_module
from agent.nodes.generate_counterexamples import _build_deterministic_test


def _contracts(*ids: str) -> list[dict[str, Any]]:
    return [
        {
            "id": contract_id,
            "expected_behavior": "",
            "requirement": "",
        }
        for contract_id in ids
    ]


def test_the_auth_template_belongs_to_the_auth_family() -> None:
    """A change whose contracts name AUTH-01 still gets the guard test."""
    source = _build_deterministic_test(_contracts("AUTH-01"))
    assert source.strip(), "an AUTH change must still get its counterexample"
    assert "SpecProofGeneratedTest" in source


def test_a_change_with_no_matching_family_gets_no_test() -> None:
    """The honest answer when nothing can be executed: NO test."""
    source = _build_deterministic_test(_contracts("BACKWARD_COMPATIBLE-01"))
    assert not source.strip(), (
        "a change whose contracts name no family this tier can execute must "
        "produce no test — writing the AUTH test anyway is what produced the "
        "false regression (#1638)"
    )


def test_the_other_families_keep_their_own_templates() -> None:
    """The AUTH template being conditional must not empty the other families."""
    source = _build_deterministic_test(_contracts("CACHE-01"))
    assert source.strip(), "a CACHE change must still get its counterexample"


def test_the_node_says_why_there_is_no_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test ⇒ the record says so (and the differential reports UNVERIFIED)."""
    workspace = tmp_path / "head"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "pom.xml").write_text(
        "<project><groupId>com.specproof</groupId></project>", encoding="utf-8"
    )

    async def _no_llm(*_a: Any, **_k: Any) -> Any:
        return gen_module.GenerationResult(
            source="deterministic_template", code="", compile_exit_code=-1, attempt=0
        )

    monkeypatch.setattr(gen_module, "_generate_with_compile_loop", _no_llm)
    monkeypatch.setattr(gen_module, "refuse_to_pollute_a_checkout", lambda _: "")

    result = gen_module.generate_counterexamples_node(
        {
            "head_workspace": str(workspace),
            "app_dir": "",
            "static_findings": [],
            "confirmed_findings": [],
            "contracts": _contracts("BACKWARD_COMPATIBLE-01"),
            "requirement_text": "",
            "changed_symbols": [],
        }
    )

    assert result["generated_tests_path"] == "", (
        "no matching family means no test — the node must not write one"
    )
    errors = " ".join(result["generation_record"]["errors"])
    assert "No deterministic template matches" in errors, errors
