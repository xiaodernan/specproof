"""model_router_graph — the model drives the state machine (LLM state flow).

The sibling graphs in this directory are witnesses: deterministic nodes that
at most knock the model once to observe it. This graph is different. Here the
MODEL is the router: its structured output (a route label) is read by a
conditional edge that selects the NEXT STATE, and a second model call writes
the content on the chosen branch. That is the "通过大模型分析能力实现状态流转
和内容输出" lane — the model both decides where to go and says what is there.

Two modes, one graph:

* **offline witness** (default; CI never spends a token) — no model call. The
  router uses a deterministic, inspectable fingerprint of the query so the
  graph's shape (conditional edge → branch → guard → report) is still exercised
  and asserted. ``route_source`` says ``witness`` and the verdict is ``HELD``.
* **live strike** (``SPECPROOF_MODEL_ROUTER_LIVE=1``) — the router calls the real
  provider with ``response_format={"type":"json_object"}`` and asks for one of
  the three route labels. That label is validated against an allowlist (a model
  hallucinating a route cannot escape the graph); the conditional edge follows
  it; the branch node then writes Chinese/English content with the frozen codex
  prefix and ``prompt_cache_key`` (the same cache sandwich that measures ~95%
  cached tokens on this gateway).

Discipline (inherited from the whole StateGraph family): the model may route and
may write, but it may NEVER rule. ``guard_node`` refuses any branch content that
claims a verdict (通过/阻断/approved/blocked/release) — the verdict here is only
about the graph's own integrity (HELD / ROUTE-DRIFT / VERDICT-LEAK), never about
an exhibit.

Usage:
    python agent/graphs/model_router_graph.py "权限校验的回归怎么定位" [--locale zh]
    SPECPROOF_MODEL_ROUTER_LIVE=1 python agent/graphs/model_router_graph.py "..."  # spends tokens
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LANES = ("evidence", "worldbook", "nextstep")
#: The model must answer with EXACTLY one of these. Anything else is ROUTE-DRIFT.
_ROUTE_ALLOWLIST = frozenset(LANES)
_VERDICT_WORDS = re.compile(
    r"已通过|未通过|验收通过|阻断|批准发布|release approved|\bapproved\b|\bblocked\b",
    re.IGNORECASE,
)


class ModelRouterState(TypedDict, total=False):
    query: str
    locale: str
    live: bool
    route: str
    route_source: str
    route_raw: str
    rationale: str
    content: str
    model: str
    usage: dict[str, Any]
    verdict: str
    detail: str
    report_path: str
    generated_utc: str


# ---------------------------------------------------------------------------
# Route selection — the node whose OUTPUT drives the conditional edge.
# ---------------------------------------------------------------------------

def _witness_route(query: str) -> str:
    """Deterministic, inspectable lane choice; no model, no token."""
    digest = hashlib.sha256(query.strip().encode("utf-8")).hexdigest()
    return LANES[int(digest[:8], 16) % len(LANES)]


def _router_messages(locale: str, query: str) -> list[Any]:
    from api.system_codex import codex_first
    from providers.base import LLMMessage

    if locale == "en":
        role = (
            "You are a router for SpecProof. Choose exactly ONE lane for the reader's "
            "question and answer in strict JSON: {\"route\": \"evidence|worldbook|nextstep\", "
            "\"rationale\": \"one short sentence\"}.\n"
            "evidence = how a verification conclusion/evidence was reached; "
            "worldbook = a fact recorded in SpecProof's own history/ledger; "
            "nextstep = what to do next in the product.\n"
            "You never approve, block, or grade anything. Output JSON only."
        )
    else:
        role = (
            "你是 SpecProof 的路由。为读者的问题选且只选一条车道，用严格 JSON 回答："
            "{\"route\": \"evidence|worldbook|nextstep\", \"rationale\": \"一句话\"}。\n"
            "evidence=一次验收的结论与证据怎么来的；worldbook=本仓正史/账本里记过的事实；"
            "nextstep=在产品里接下来该做什么。\n"
            "你绝不批准、阻断或评判任何东西。只输出 JSON。"
        )
    return codex_first(
        [LLMMessage(role="system", content=role), LLMMessage(role="user", content=query[:480])],
        locale,
    )


def cached_tokens_of(usage: dict[str, Any]) -> int:
    """Read the cache-hit count from whichever usage shape the gateway returns.

    aizzz / the normalized provider use ``prompt_cache_hit_tokens``; raw OpenAI
    responses nest it under ``prompt_tokens_details.cached_tokens``. Reading only
    one shape is exactly what makes a healthy cache 'look' like it dropped.
    """
    try:
        value = int(usage.get("prompt_cache_hit_tokens") or 0)
        if not value:
            details = usage.get("prompt_tokens_details") or {}
            value = int(details.get("cached_tokens") or 0)
        return max(0, value)
    except (AttributeError, ValueError, TypeError):
        return 0


def _parse_route(raw: str) -> tuple[str, str]:
    """Return (route, rationale). A hallucinated route becomes the empty string."""
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        m = re.search(r"\{.*\}", raw or "", re.DOTALL)
        if not m:
            return "", "unparseable route response"
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            return "", "unparseable route response"
    route = str(obj.get("route", "")).strip().lower()
    rationale = str(obj.get("rationale", ""))[:240]
    if route not in _ROUTE_ALLOWLIST:
        return "", f"route {route!r} not in allowlist"
    return route, rationale


def intake_node(state: ModelRouterState) -> ModelRouterState:
    query = (state.get("query") or "").strip()
    locale = state.get("locale") or "zh"
    live = bool(state.get("live") or os.getenv("SPECPROOF_MODEL_ROUTER_LIVE") == "1")
    if not query:
        return {"verdict": "MISSING-QUERY", "detail": "empty query", "live": live, "locale": locale}
    return {
        "query": query,
        "locale": locale,
        "live": live,
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "verdict": "INTAKE",
    }


def route_node(state: ModelRouterState) -> ModelRouterState:
    """Pick the route. In witness mode it is deterministic; in live mode the model decides."""
    if state.get("verdict") not in ("INTAKE", None):
        return {}
    query = state.get("query") or ""
    if not state.get("live"):
        return {"route": _witness_route(query), "route_source": "witness", "verdict": "ROUTED"}
    try:
        from providers.openai_compatible import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(timeout=120.0)
        try:
            response = asyncio.run(provider.chat(
                _router_messages(state.get("locale") or "zh", query),
                response_format={"type": "json_object"},
                opts={"prompt_cache_key": "specproof-model-router"},
            ))
        finally:
            asyncio.run(provider.close())
        route, rationale = _parse_route(response.content or "")
        usage = dict(response.usage or {})
        cached = cached_tokens_of(usage)
        return {
            "route": route,
            "route_raw": (response.content or "")[:400],
            "route_source": "model",
            "rationale": rationale,
            "model": response.model or "",
            "usage": {**usage, "cached_tokens_seen": cached},
            "verdict": "ROUTED" if route else "ROUTE-DRIFT",
        }
    except Exception as exc:  # noqa: BLE001 - an honest failure, never a fabricated route
        return {"route": "", "route_source": "model-error", "verdict": "ROUTE-DRIFT",
                "detail": f"{type(exc).__name__}: {exc}"[:240]}


def _branch_content(lane: str, state: ModelRouterState) -> ModelRouterState:
    """Write content on the chosen branch. Live mode writes with the model; witness
    mode writes a deterministic, honest sentence (no fabricated facts)."""
    locale = state.get("locale") or "zh"
    query = state.get("query") or ""
    head = {
        "evidence": ("证据车道", "evidence lane"),
        "worldbook": ("世界书车道", "worldbook lane"),
        "nextstep": ("下一步车道", "next-step lane"),
    }[lane][0 if locale == "zh" else 1]
    if not state.get("live"):
        line = (
            f"[{head}] 已按确定性见证模式选中此车道（未敲模型、未花 token）：{query[:80]}"
            if locale == "zh"
            else f"[{head}] selected in deterministic witness mode (no model call, no token): {query[:80]}"
        )
        return {"content": line, "verdict": "ANSWERED"}
    try:
        from api.system_codex import codex_first
        from providers.base import LLMMessage
        from providers.openai_compatible import OpenAICompatibleProvider

        if locale == "en":
            ask = f"Answer on the {lane} lane, in English, plainly and briefly: {query[:480]}"
        else:
            ask = f"在{lane}车道上，用中文简明回答：{query[:480]}"
        provider = OpenAICompatibleProvider(timeout=120.0)
        try:
            response = asyncio.run(provider.chat(
                codex_first([LLMMessage(role="user", content=ask)], locale),
                opts={"prompt_cache_key": "specproof-model-router"},
            ))
        finally:
            asyncio.run(provider.close())
        return {"content": (response.content or "").strip()[:1200], "verdict": "ANSWERED"}
    except Exception as exc:  # noqa: BLE001
        return {"content": "", "verdict": "MODEL-FAILURE", "detail": f"{type(exc).__name__}: {exc}"[:240]}


def evidence_node(state: ModelRouterState) -> ModelRouterState:
    return _branch_content("evidence", state)


def worldbook_node(state: ModelRouterState) -> ModelRouterState:
    return _branch_content("worldbook", state)


def nextstep_node(state: ModelRouterState) -> ModelRouterState:
    return _branch_content("nextstep", state)


def _route_to_branch(state: ModelRouterState) -> str:
    """The conditional edge: the route label selected above becomes the next state."""
    route = state.get("route") or ""
    return route if route in _ROUTE_ALLOWLIST else "guard"


def guard_node(state: ModelRouterState) -> ModelRouterState:
    """The graph may report its own integrity, but content may never rule."""
    if state.get("verdict") in ("ROUTE-DRIFT", "MODEL-FAILURE", "MISSING-QUERY"):
        return {}
    if _VERDICT_WORDS.search(state.get("content") or ""):
        return {"verdict": "VERDICT-LEAK",
                "detail": "model claimed a verdict — refused; this graph never grades an exhibit"}
    return {"verdict": "HELD", "detail": "route allowlisted, content verdict-free"}


def report_node(state: ModelRouterState) -> ModelRouterState:
    day = (state.get("generated_utc") or datetime.now(UTC).isoformat())[:10]
    out_dir = Path(os.getenv("SPECPROOF_MODEL_ROUTER_WITNESS_DIR",
                             str(ROOT / "evidence" / "model-router")))
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"model-router-{day}.json"
    payload = {
        "lane": "model_router",
        "query_chars": len(state.get("query") or ""),
        "locale": state.get("locale") or "zh",
        "live": bool(state.get("live")),
        "route": state.get("route") or "",
        "route_source": state.get("route_source") or "",
        "rationale": state.get("rationale") or "",
        "content": state.get("content") or "",
        "model": state.get("model") or "",
        "usage": state.get("usage") or {},
        "verdict": state.get("verdict") or "",
        "detail": state.get("detail") or "",
        "generated_utc": state.get("generated_utc") or "",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"report_path": str(path)}


def build_model_router_graph() -> Any:
    g: Any = StateGraph(ModelRouterState)
    g.add_node("intake", intake_node)
    g.add_node("route", route_node)
    g.add_node("evidence", evidence_node)
    g.add_node("worldbook", worldbook_node)
    g.add_node("nextstep", nextstep_node)
    g.add_node("guard", guard_node)
    g.add_node("report", report_node)
    g.set_entry_point("intake")
    g.add_edge("intake", "route")
    # The model's route label drives which state runs next.
    g.add_conditional_edges("route", _route_to_branch,
                            {"evidence": "evidence", "worldbook": "worldbook",
                             "nextstep": "nextstep", "guard": "guard"})
    g.add_edge("evidence", "guard")
    g.add_edge("worldbook", "guard")
    g.add_edge("nextstep", "guard")
    g.add_edge("guard", "report")
    g.add_edge("report", END)
    return g.compile()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("query", nargs="?", default="权限校验的回归怎么定位")
    ap.add_argument("--locale", default="zh", choices=["zh", "en"])
    args = ap.parse_args()
    result = build_model_router_graph().invoke({"query": args.query, "locale": args.locale})
    print(json.dumps({k: result.get(k) for k in
                      ("route", "route_source", "verdict", "content", "report_path", "usage")},
                     ensure_ascii=False, indent=2))
    return 0 if result.get("verdict") in ("HELD", "ANSWERED") else 1


if __name__ == "__main__":
    raise SystemExit(main())
