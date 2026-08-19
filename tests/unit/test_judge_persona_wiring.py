"""Wiring tests: NO_FAKE_PASS_SYSTEM_PROMPT reaches both LLM judgement paths.

The persona is wired through providers/judge_persona.build_judge_prompt, which
APPENDS it after the caller's base prompt so the stable base-prompt prefix
stays byte-identical at the front (KV-cache-friendly ordering). These tests
inject fake providers and assert:

- the review-court model layer (_llm_defense_materials) appends the persona
  after the base defense prompt when an LLM client is configured;
- the contract-compile LLM candidate path (_llm_compile_contracts) appends
  it after the base contract validation prompt likewise;
- the deterministic paths (no LLM client configured) stay byte-unchanged
  and never carry the persona;
- the persona clauses are present via the stable strings pinned verbatim in
  tests/unit/test_judge_persona.py.

No network, no environment, no real API keys.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import Any, cast

from agent.contracts.records import checker_version_for
from agent.nodes.compile_contracts import (
    _LLM_CONTRACT_PROMPT,
    _llm_compile_contracts,
    compile_contracts_node,
)
from agent.nodes.review_court import (
    _LLM_DEFENSE_PROMPT,
    _llm_defense_materials,
    build_llm_defense_producer,
    review_court_node,
    run_review_court,
)
from agent.state import Phase0State
from providers.judge_persona import NO_FAKE_PASS_SYSTEM_PROMPT

# Stable persona clauses pinned verbatim in tests/unit/test_judge_persona.py.
STABLE_CLAUSES: tuple[str, ...] = (
    "JUDGE INTEGRITY PERSONA — NO FAKE PASSES",
    "Never report a test as passed unless you actually executed it.",
    "Never skip a gate silently",
    "Every verdict must cite the evidence ids it is based on.",
    "Refuse to fabricate run output",
    "除非真正执行过该测试",
)

AUTH_ONLY_TEXT = "Unauthenticated requests must receive 401."


class CapturingProvider:
    """Fake provider seam: records every chat() call and answers canned JSON."""

    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[list[Any]] = []

    async def chat(self, messages: list[Any], **kwargs: Any) -> Any:
        self.calls.append(messages)
        return SimpleNamespace(content=self.content)


def _defense_json() -> str:
    return json.dumps([{
        "id": "STATIC-AUTH-01",
        "defense_argument": "refactor only",
        "candidate_confidence": 0.5,
        "is_false_positive": False,
    }])


def _contract_json() -> str:
    return json.dumps([{
        "id": "AUTH-01",
        "checker_type": "http",
        "requirement": "Unauthenticated requests must receive 401",
        "expected_behavior": "401 without auth",
    }])


def _court_state() -> Phase0State:
    return cast(Phase0State, {
        "static_findings": [{
            "id": "STATIC-AUTH-01",
            "severity": "MAJOR",
            "type": "annotation_removed",
            "description": "@PreAuthorize removed",
            "evidence_type": "static_regex_analysis",
            "confidence": 0.8,
        }],
        "diff_results": [],
        "contracts": [],
        "repo_path": "",
    })


def _assert_stable_clauses(content: str) -> None:
    for clause in STABLE_CLAUSES:
        assert clause in content, f"missing stable persona clause: {clause!r}"


class TestReviewCourtModelLayerWiring:
    def test_defense_prompt_appends_persona_after_base(self) -> None:
        provider = CapturingProvider(_defense_json())
        candidates = [{"id": "STATIC-AUTH-01", "source": "static_analysis"}]

        output = asyncio.run(_llm_defense_materials(provider, candidates))

        assert output["parse_failed"] is False
        assert len(output["defense_materials"]) == 1
        assert len(provider.calls) == 1
        messages = provider.calls[0]
        assert len(messages) == 1
        content = str(messages[0].content)
        # The stable base-prompt head stays byte-identical at the front...
        assert content.startswith(_LLM_DEFENSE_PROMPT.split("{candidates_json}")[0])
        # ...and the persona rides at the very tail (KV-cache ordering).
        assert content.endswith(NO_FAKE_PASS_SYSTEM_PROMPT)
        _assert_stable_clauses(content)

    def test_persona_reaches_court_only_when_llm_client_configured(self) -> None:
        provider = CapturingProvider(_defense_json())
        producer = build_llm_defense_producer(provider)

        result = run_review_court(_court_state(), model_produce_defense=producer)

        assert len(provider.calls) == 1
        content = str(provider.calls[0][0].content)
        assert content.endswith(NO_FAKE_PASS_SYSTEM_PROMPT)
        _assert_stable_clauses(content)
        assert len(result["confirmed_findings"]) == 1

        # No LLM client configured -> the deterministic court runs verbatim,
        # builds no prompt and never touches the persona.
        deterministic = run_review_court(_court_state())
        assert deterministic == run_review_court(_court_state())
        dumped = json.dumps(deterministic, sort_keys=True)
        assert "JUDGE INTEGRITY PERSONA" not in dumped
        assert NO_FAKE_PASS_SYSTEM_PROMPT not in dumped


class TestCompileContractLlmWiring:
    def test_llm_compile_prompt_appends_persona_after_base(self) -> None:
        provider = CapturingProvider(_contract_json())

        raw, problems = asyncio.run(_llm_compile_contracts(AUTH_ONLY_TEXT, provider))

        assert problems == []
        assert len(raw) == 1
        assert raw[0]["id"] == "AUTH-01"
        assert len(provider.calls) == 1
        content = str(provider.calls[0][0].content)
        assert content.startswith(_LLM_CONTRACT_PROMPT.split("{spec_text}")[0])
        assert content.endswith(NO_FAKE_PASS_SYSTEM_PROMPT)
        _assert_stable_clauses(content)


class TestDeterministicPathsUnchanged:
    def test_review_court_deterministic_output_has_no_persona(self) -> None:
        first = review_court_node(_court_state())
        second = review_court_node(_court_state())
        assert first == second
        dumped = json.dumps(first, sort_keys=True)
        assert "JUDGE INTEGRITY PERSONA" not in dumped
        assert NO_FAKE_PASS_SYSTEM_PROMPT not in dumped

    def test_compile_deterministic_contracts_byte_unchanged(self) -> None:
        state = cast(Phase0State, {
            "requirement_text": AUTH_ONLY_TEXT,
            "use_llm": False,
        })
        result = compile_contracts_node(state)
        # Byte-identical to the pre-wiring deterministic output.
        assert result["contracts"] == [{
            "id": "AUTH-01",
            "requirement": AUTH_ONLY_TEXT,
            "checker_type": "http",
            "expected_behavior": (
                "Unauthenticated requests must receive 401 Unauthorized"
            ),
            "result": "UNVERIFIED",
            "evidence_ref": None,
            "approved": True,
            "version": 1,
            "checker_version": checker_version_for("http"),
        }]
        dumped = json.dumps(result, sort_keys=True)
        assert "JUDGE INTEGRITY PERSONA" not in dumped
        assert NO_FAKE_PASS_SYSTEM_PROMPT not in dumped

    def test_base_prompt_templates_never_embed_the_persona(self) -> None:
        # The persona may only ride the LLM call via build_judge_prompt —
        # never baked into the static base prompt templates themselves.
        assert "JUDGE INTEGRITY PERSONA" not in _LLM_DEFENSE_PROMPT
        assert "JUDGE INTEGRITY PERSONA" not in _LLM_CONTRACT_PROMPT
