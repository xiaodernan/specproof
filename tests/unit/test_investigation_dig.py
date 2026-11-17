"""investigation_dig_graph + craft.investigators — unit tests (offline; no network)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.graphs import investigation_dig_graph as G


REPO = Path(__file__).resolve().parents[2]


def test_role_payload_explorer_bounded() -> None:
    from craft.investigators import _role_payload
    facts = _role_payload(REPO, "explorer")
    assert len(facts) <= 4004


def test_role_payload_tester_bounded() -> None:
    from craft.investigators import _role_payload
    facts = _role_payload(REPO, "tester")
    assert len(facts) <= 4004


def test_role_payload_security_bounded() -> None:
    from craft.investigators import _role_payload
    facts = _role_payload(REPO, "security")
    assert len(facts) <= 2004


def test_workspace_facts_bounded() -> None:
    from craft.investigators import _workspace_facts
    facts = _workspace_facts(REPO)
    assert len(facts) <= 4004


def test_graph_compiles_with_expected_nodes() -> None:
    g = G.build_investigation_dig_graph()
    nodes = set(g.nodes.keys()) if hasattr(g, "nodes") else set()
    assert {"intake", "strike", "verdict", "report"}.issubset(nodes)


async def _stub_investigate_factory(verdict: str):
    async def _fake(workspace, question, **kwargs):
        return {
            "verdict": verdict,
            "findings": [{"role": "explorer", "claim": "stubbed claim", "evidence": "facts-pack", "confidence": 0.5}],
            "agents": [{"name": "investigate_explorer", "outcome": "ok", "duration_ms": 10, "tokens": 30}],
            "total_tokens_used": 30,
            "generation_time_ms": 42,
        }
    return _fake


def test_strike_node_dates_evidence_gathered(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(workspace, question, **kwargs):
        return {
            "verdict": "EVIDENCE-GATHERED",
            "findings": [{"role": "explorer", "claim": "stubbed claim", "evidence": "facts-pack", "confidence": 0.5}],
            "agents": [{"name": "investigate_explorer", "outcome": "ok", "duration_ms": 10, "tokens": 30}],
            "total_tokens_used": 30,
            "generation_time_ms": 42,
        }

    monkeypatch.setattr(G, "investigate", _fake, raising=False)
    out = G.strike_node(G.intake_node({"question": "what is this"}))
    assert out["verdict"] == "EVIDENCE-GATHERED"
    assert out["agents"][0]["name"] == "investigate_explorer"


def test_strike_node_insufficient_when_provider_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake(workspace, question, **kwargs):
        return {
            "verdict": "INSUFFICIENT",
            "findings": [],
            "agents": [],
            "total_tokens_used": 0,
            "generation_time_ms": 0,
        }

    monkeypatch.setattr(G, "investigate", _fake, raising=False)
    out = G.strike_node(G.intake_node({"question": "what is this"}))
    assert out["verdict"] == "INSUFFICIENT"
    assert out["agents"] == []


def test_subagentspec_integrity_when_exhausted() -> None:
    from craft.investigators import investigate

    class _Response:
        content = "这是一个商店管理后台，前端用了 Next.js，后端用了 FastAPI。"
        usage = {"prompt_tokens": 120, "completion_tokens": 32}
        model = "gpt-6.1-terra"

    class _LLM:
        def __init__(self, **_): pass

        async def chat(self, messages, *, label="", kind=None, job_id="", step_id="", timeout=None, thinking=False, response_format=None, estimated_prompt_tokens=0, **_):
            return _Response()

    result = asyncio.run(investigate(Path(__file__).resolve().parents[2], "本仓库做了什么？", llm_client=_LLM(), timeout=5.0))
    assert "verdict" in result
    assert result["verdict"] in {"EVIDENCE-GATHERED", "INSUFFICIENT"}
    assert isinstance(result["agents"], list)
