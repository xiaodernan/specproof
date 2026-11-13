"""The generation prompt must ask about THE CHANGE, not about a story it invented.

WHY THIS FILE EXISTS. The prompt used to open with a fixed scenario: "A PR
removed an authorization guard (e.g. @PreAuthorize) from a mutating endpoint.
Unauthenticated requests must be rejected with 401 and must not modify
database state." — and it never told the model what actually changed.

So for EVERY change the model wrote *that* story's test. On the real model
(six negative cases, ledger #1638) that produced the one false positive in
the set: a PR that merely ADDED a product-detail endpoint got a test
asserting that an unauthenticated request is rejected, the test failed on
Head, and the review court reported a MAJOR regression. The change had
nothing to do with the assertion.

Two things are pinned here:

* the prompt carries WHAT CHANGED (the changed symbols) and asks for a test
  of THAT change — including the branch where the change is not a guard
  change at all;
* the node really threads the state's ``changed_symbols`` into the call,
  so the prompt's new section is not an empty promise.

WHAT THIS DOES NOT CLAIM. It does not prove the model now writes better
tests — that is measured by re-running the evaluation on the real model
(#1638's queue). It proves the prompt stops *asserting* a scenario the
change may not have, and that the change's own symbols are in front of the
model when it writes.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import agent.nodes.generate_counterexamples as gen_module
from agent.nodes.generate_counterexamples import (
    _JUNIT_GENERATION_PROMPT,
    _llm_generate_junit,
    generate_counterexamples_node,
)


class _CapturingProvider:
    """A provider that records the prompt it was handed."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def chat(self, messages: Any, **_: Any) -> SimpleNamespace:
        self.prompts.append(messages[0].content)
        return SimpleNamespace(content="class SpecProofGeneratedTest {}")


def test_the_prompt_does_not_assert_a_fixed_scenario() -> None:
    """The old opening line told the model what the change WAS."""
    assert "A PR removed an authorization guard" not in _JUNIT_GENERATION_PROMPT, (
        "the prompt still asserts a scenario the change under review may not "
        "have — that is how an added endpoint produced a guard test"
    )
    assert "the change under review" in _JUNIT_GENERATION_PROMPT.lower()


def test_the_prompt_says_what_to_do_when_the_change_is_not_a_guard_change() -> None:
    """The other branch has to be IN the prompt, or the model will still
    write the guard test for a change that removed no guard."""
    lowered = _JUNIT_GENERATION_PROMPT.lower()
    assert "if the change did something else" in lowered, (
        "the prompt must tell the model what to do when the change is not a "
        "guard change"
    )


def test_the_changed_symbols_reach_the_prompt() -> None:
    provider = _CapturingProvider()
    original = gen_module._get_provider
    gen_module._get_provider = lambda: provider  # type: ignore[assignment]
    try:
        asyncio.run(
            _llm_generate_junit(
                [],
                [],
                requirement_text="a new product detail endpoint",
                changed_symbols=[
                    "com.specproof.demo.controller.ProductController#get",
                ],
            )
        )
    finally:
        gen_module._get_provider = original  # type: ignore[assignment]

    assert provider.prompts, "the provider was never consulted"
    prompt = provider.prompts[0]
    assert "Changed symbols:" in prompt, prompt[:400]
    assert "com.specproof.demo.controller.ProductController#get" in prompt


def test_the_node_threads_the_changed_symbols_into_the_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prompt's new section must not be an empty promise: the node has
    to hand the state's changed symbols over."""
    seen: dict[str, Any] = {}

    async def _fake_loop(
        workspace: str,
        findings: list[dict[str, Any]],
        contracts: list[dict[str, Any]],
        requirement_text: str,
        job_id: str | None = None,
        changed_symbols: list[str] | None = None,
    ) -> Any:
        seen["changed_symbols"] = changed_symbols
        return gen_module.GenerationResult(
            source="llm_generated", code="", compile_exit_code=0, attempt=1
        )

    monkeypatch.setattr(gen_module, "_generate_with_compile_loop", _fake_loop)
    monkeypatch.setattr(gen_module, "_get_provider", lambda: _CapturingProvider())
    monkeypatch.setattr(gen_module, "refuse_to_pollute_a_checkout", lambda _: "")

    workspace = tmp_path / "head"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "pom.xml").write_text("<project/>", encoding="utf-8")
    generate_counterexamples_node(
        {
            "head_workspace": str(workspace),
            "app_dir": "",
            "static_findings": [],
            "confirmed_findings": [],
            "contracts": [],
            "requirement_text": "",
            "changed_symbols": ["com.specproof.demo.controller.ProductController#get"],
        }
    )

    assert seen.get("changed_symbols") == [
        "com.specproof.demo.controller.ProductController#get"
    ], seen
