"""Compile-contracts node execution tests (#192) — honest counters at the
node boundary, written WITH the landing (not backfilled).

The node's LLM seam (``_get_provider``) is stubbed with preset providers;
everything else runs for real (the empty-text short circuit, the
registry-approved path, the rule/LLM fork, the LLM pass with its degrade
paths). One case per outcome word in COMPILE_OUTCOMES:

- empty_input: no requirement text — nothing to compile;
- approved_loaded: registry-approved rows take precedence over compilation;
- rules_sufficient: >=2 rule matches — the LLM is never attempted (witness:
  a chat stub that would raise proves the provider was untouched);
- llm_disabled: sparse rules + use_llm=False — _get_provider is never
  called (witness: a factory that would raise);
- llm_unavailable: sparse rules + LLM wanted + no provider configured;
- llm_replaced: the LLM pass replaced the deterministic candidate list;
- llm_degraded: the LLM pass failed — the rule list is kept;

plus compile_contracts_runs_total on every path and a drift gate binding
the parity family's regex words to COMPILE_OUTCOMES and to the source
literals.
"""

from __future__ import annotations

import re
import types
from pathlib import Path

import pytest

from agent.nodes.compile_contracts import (
    COMPILE_OUTCOMES,
    compile_contracts_node,
)
from observability.metrics import snapshot

ROOT = Path(__file__).resolve().parents[2]

# Same fixture texts as tests/unit/test_compile_report.py — sparse text has
# ZERO rule matches, AUTH_ONLY exactly one, TWO_FAMILY two (LLM skipped).
SPARSE_TEXT = "Users must be able to change their email address."
AUTH_ONLY_TEXT = "Unauthenticated requests must receive 401."
TWO_FAMILY_TEXT = (
    "Unauthenticated requests must receive 401.\n"
    "Duplicate emails must be rejected with a unique constraint."
)

# Derived from the declaration — a new word extends the delta table with it.
_COUNTERS = ("compile_contracts_runs_total",) + tuple(
    f"compile_contracts_outcomes_{word}_total"
    for word in sorted(COMPILE_OUTCOMES)
)


def _counter(name: str) -> float:
    # The registry stores BARE names — the specproof_ prefix is added by
    # render_text only.
    return snapshot()["counters"].get(name, 0.0)


def _before() -> dict[str, float]:
    return {name: _counter(name) for name in _COUNTERS}


def _deltas(before: dict[str, float]) -> dict[str, float]:
    return {name: _counter(name) - start for name, start in before.items()}


def _only(*words: str) -> dict[str, float]:
    """Expected deltas: runs+1 and exactly the named outcome words +1."""
    deltas = dict.fromkeys(_COUNTERS, 0.0)
    deltas["compile_contracts_runs_total"] = 1.0
    for word in words:
        deltas[f"compile_contracts_outcomes_{word}_total"] = 1.0
    return deltas


class _FakeProvider:
    """Provider seam double: answers chat() with canned content or raises."""

    def __init__(self, content: str = "", error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls = 0

    async def chat(self, messages: object = None, timeout: float = 0.0) -> object:  # noqa: ARG002
        self.calls += 1
        if self.error is not None:
            raise self.error
        return types.SimpleNamespace(content=self.content)


def _patch_provider(monkeypatch: pytest.MonkeyPatch, provider: object) -> None:
    def factory() -> object:
        return provider

    monkeypatch.setattr("agent.nodes.compile_contracts._get_provider", factory)


def test_empty_input_counts_empty_input() -> None:
    before = _before()
    result = compile_contracts_node({"requirement_text": ""})  # type: ignore[arg-type]
    assert result["contracts"] == []
    assert _deltas(before) == _only("empty_input")


def test_approved_loaded_counts_approved_loaded() -> None:
    before = _before()
    state = {
        "requirement_text": SPARSE_TEXT,
        "approved_contracts": [
            {"id": "AUTH-01", "checker_type": "http", "requirement": "r",
             "expected_behavior": "e"}
        ],
    }
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    assert [c["id"] for c in result["contracts"]] == ["AUTH-01"]
    assert result["contracts"][0]["approved"] is True
    assert _deltas(before) == _only("approved_loaded")


def test_rules_sufficient_never_touches_the_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    # A chat stub that would record (and could raise) proves the LLM seam was
    # not exercised: a wrong fork turns this case red via bomb.calls and the
    # word (degrades into llm_degraded).
    bomb = _FakeProvider(error=AssertionError("LLM must not be called"))
    _patch_provider(monkeypatch, bomb)
    before = _before()
    result = compile_contracts_node({"requirement_text": TWO_FAMILY_TEXT})  # type: ignore[arg-type]
    assert len(result["contracts"]) >= 2
    assert bomb.calls == 0
    assert _deltas(before) == _only("rules_sufficient")


def test_llm_disabled_when_use_llm_false(monkeypatch: pytest.MonkeyPatch) -> None:
    def bomb_factory() -> object:
        raise AssertionError("_get_provider must not be called when use_llm=False")

    monkeypatch.setattr("agent.nodes.compile_contracts._get_provider", bomb_factory)
    before = _before()
    state: dict[str, object] = {"requirement_text": AUTH_ONLY_TEXT, "use_llm": False}
    result = compile_contracts_node(state)  # type: ignore[arg-type]
    assert [c["id"] for c in result["contracts"]] == ["AUTH-01"]
    assert _deltas(before) == _only("llm_disabled")


def test_llm_unavailable_counts_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_provider(monkeypatch, None)
    before = _before()
    result = compile_contracts_node({"requirement_text": SPARSE_TEXT})  # type: ignore[arg-type]
    assert result["compile_report"]["degrade_reasons"] == [
        "LLM unavailable: LLM_API_KEY not configured"
    ]
    assert _deltas(before) == _only("llm_unavailable")


def test_llm_replaced_counts_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProvider(
        '[{"id": "LLM-01", "checker_type": "http", "requirement": "r", '
        '"expected_behavior": "e"}]'
    )
    _patch_provider(monkeypatch, fake)
    before = _before()
    result = compile_contracts_node({"requirement_text": AUTH_ONLY_TEXT})  # type: ignore[arg-type]
    assert [c["id"] for c in result["contracts"]] == ["LLM-01"]
    assert fake.calls == 1
    assert _deltas(before) == _only("llm_replaced")


def test_llm_degraded_keeps_the_rule_list(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeProvider(error=RuntimeError("boom"))
    _patch_provider(monkeypatch, fake)
    before = _before()
    result = compile_contracts_node({"requirement_text": AUTH_ONLY_TEXT})  # type: ignore[arg-type]
    assert [c["id"] for c in result["contracts"]] == ["AUTH-01"]
    assert any(
        "LLM call failed" in reason
        for reason in result["compile_report"]["degrade_reasons"]
    )
    assert _deltas(before) == _only("llm_degraded")


def test_outcome_vocabulary_matches_parity_and_source() -> None:
    from tests.unit.test_observability_metric_parity import CONCATENATED_FAMILIES

    source = (ROOT / "agent" / "nodes" / "compile_contracts.py").read_text(
        encoding="utf-8"
    )
    literals = set(
        re.findall(r'incr\("compile_contracts_outcomes_([a-z_]+)_total"\)', source)
    )
    assert literals == set(COMPILE_OUTCOMES), (
        f"source literals {sorted(literals)} != declared vocabulary "
        f"{sorted(COMPILE_OUTCOMES)}"
    )
    assert source.count('incr("compile_contracts_runs_total")') == 1

    pattern, _ = CONCATENATED_FAMILIES["compile_contracts"]
    parity_words = set(
        re.search(r"\(([^()]+)\)", pattern.pattern).group(1).split("|")  # type: ignore[union-attr]
    )
    assert parity_words == set(COMPILE_OUTCOMES), (
        f"parity family words {sorted(parity_words)} != declared vocabulary "
        f"{sorted(COMPILE_OUTCOMES)}"
    )
