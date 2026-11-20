"""model_router_graph — the model-driven state machine, measured offline.

The conditional edge is the whole point: the route label (from a witness
fingerprint here, from the model's structured output in live mode) selects the
branch node. No token is spent in CI.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.graphs.model_router_graph import (
    LANES,
    _parse_route,
    _route_to_branch,
    _witness_route,
    build_model_router_graph,
    cached_tokens_of,
    guard_node,
    intake_node,
)


@pytest.fixture()
def witness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "router-witness"
    monkeypatch.setenv("SPECPROOF_MODEL_ROUTER_WITNESS_DIR", str(d))
    monkeypatch.delenv("SPECPROOF_MODEL_ROUTER_LIVE", raising=False)
    return d


def test_graph_is_a_real_stategraph() -> None:
    assert build_model_router_graph() is not None


def test_route_allowlist_rejects_hallucination() -> None:
    route, _ = _parse_route('{"route": "NONSENSE", "rationale": "x"}')
    assert route == ""
    route, why = _parse_route("not json")
    assert route == "" and why
    route, _ = _parse_route('{"route": "EVIDENCE", "rationale": "ok"}')
    assert route == "evidence"


def test_conditional_edge_follows_the_selected_route() -> None:
    for lane in LANES:
        assert _route_to_branch({"route": lane}) == lane
    # A hallucinated route cannot escape the graph — it falls to guard.
    assert _route_to_branch({"route": "bogus"}) == "guard"


def test_witness_route_is_deterministic() -> None:
    assert _witness_route("same question") == _witness_route("same question")


def test_offline_invoke_routes_through_a_branch_and_holds(witness: Path) -> None:
    result = build_model_router_graph().invoke({"query": "权限校验的回归怎么定位", "locale": "zh"})
    assert result["route"] in LANES
    assert result["route_source"] == "witness"
    assert result["verdict"] == "HELD"
    assert result["content"]
    report = Path(str(result["report_path"]))
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["live"] is False
    assert payload["route"] == result["route"]


@pytest.mark.parametrize("usage,expected", [
    ({"prompt_cache_hit_tokens": 8029}, 8029),    # aizzz / normalized provider shape
    ({"prompt_tokens_details": {"cached_tokens": 41}}, 41),  # raw OpenAI shape
    ({"prompt_cache_hit_tokens": 0, "prompt_tokens_details": {"cached_tokens": 41}}, 41),
    ({}, 0),
    ({"prompt_cache_hit_tokens": "not-an-int"}, 0),
])
def test_cached_token_reading_survives_gateway_usage_shapes(usage: dict, expected: int) -> None:
    """A misread here is exactly what makes a healthy cache 'look' like it dropped."""
    assert cached_tokens_of(usage) == expected


def test_guard_refuses_verdict_leak() -> None:
    out = guard_node({"verdict": "ANSWERED", "content": "本次验收已通过"})
    assert out["verdict"] == "VERDICT-LEAK"


def test_empty_query_is_rejected_without_a_route() -> None:
    assert intake_node({})["verdict"] == "MISSING-QUERY"
