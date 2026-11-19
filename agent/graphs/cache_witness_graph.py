"""cache_witness_graph.py — measure prefix-cache efficiency on this host's live lane.

Two back-to-back strikes with the SAME fixed prompt under `stream=True + include_usage=True`;
the second strike's cached_tokens is the whole point of this witness.
No LLM is generated on judge — the gateway decides whether the prefix bytes match.

Pattern: intake -> strike_one -> strike_two -> verdict -> report -> END

Usage:

    python agent/graphs/cache_witness_graph.py

Writes docs/evidence/cache-witness.md + docs/evidence/cache-witness.json.
Exits 0 if cached_tokens recorded (any number), 1 if absent/err.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from langgraph.graph import END, StateGraph  # noqa: E402
from typing_extensions import TypedDict  # noqa: E402


class CacheWitnessState(TypedDict, total=False):
    started_utc: str
    prompt_tokens_a: int
    cached_tokens_a: int
    prompt_tokens_b: int
    cached_tokens_b: int
    hit_rate_b: float | None
    verdict: str
    notes: str
    report_path: str


PROMPT = (
    "用一句话确认：铁证不伪造。回答不超过 15 个汉字。"
    "这是一份重复前缀用于观察缓存命中的密文，每次与此完全相同。"
)


def _model_config() -> dict[str, Any]:
    from providers.config import load_model_config
    return load_model_config()


def _http_strike(cfg: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/chat/completions with a fixed prompt; return usage."""
    from providers.net import outbound_client

    body = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": PROMPT}],
        "max_tokens": 8,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    class _Sink:
        def __init__(self) -> None:
            self.usage: dict[str, Any] | None = None
            self.text: list[str] = []
            self.chunks = 0

        def feed(self, line: str) -> None:
            s = line.strip()
            if not s or not s.startswith("data:"):
                return
            payload = s[5:].strip()
            if payload == "[DONE]":
                return
            try:
                obj = json.loads(payload)
            except ValueError:
                return
            self.chunks += 1
            choices = obj.get("choices") or []
            if choices:
                delta = choices[0].get("delta", {})
                if delta.get("content"):
                    self.text.append(delta["content"])
            if obj.get("usage"):
                self.usage = obj["usage"]

    sink = _Sink()
    with outbound_client(timeout=90.0) as client, client.stream(
        "POST",
        cfg["base_url"].rstrip("/") + "/chat/completions",
        headers={
            "Authorization": f"Bearer {cfg['api_key']}",
            "Accept": "text/event-stream",
            "Content-Type": "application/json",
        },
        json=body,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                sink.feed(line)
    u: dict[str, Any] = sink.usage or {}
    return {
        "prompt_tokens": u.get("prompt_tokens"),
        "completion_tokens": u.get("completion_tokens"),
        "cached_tokens": (u.get("prompt_tokens_details") or {}).get("cached_tokens"),
        "chunks": sink.chunks,
    }


def intake_node(state: CacheWitnessState) -> CacheWitnessState:
    return {"started_utc": datetime.now(UTC).isoformat(timespec="seconds")}


def strike_one_node(state: CacheWitnessState) -> CacheWitnessState:
    cfg = _model_config()
    out = _http_strike(cfg)
    return {
        "prompt_tokens_a": out.get("prompt_tokens") or 0,
        "cached_tokens_a": out.get("cached_tokens") or 0,
    }


def strike_two_node(state: CacheWitnessState) -> CacheWitnessState:
    cfg = _model_config()
    out = _http_strike(cfg)
    return {
        "prompt_tokens_b": out.get("prompt_tokens") or 0,
        "cached_tokens_b": out.get("cached_tokens") or 0,
    }


def verdict_node(state: CacheWitnessState) -> CacheWitnessState:
    p = state.get("prompt_tokens_b") or 0
    c = state.get("cached_tokens_b") or 0
    hit = (c / p) if p else 0.0
    verdict = "HIT" if hit >= 0.50 else "MISS"
    return {"hit_rate_b": hit, "verdict": verdict}


def report_node(state: CacheWitnessState) -> CacheWitnessState:
    md_path = Path(os.environ.get("SPECPROOF_CACHE_WITNESS_OUT", "docs/evidence"))
    md_path.mkdir(parents=True, exist_ok=True)
    md_file = md_path / "cache-witness.md"
    js_file = md_path / "cache-witness.json"

    payload = {
        "version": 1,
        "started_utc": state.get("started_utc"),
        "prompt_tokens_a": state.get("prompt_tokens_a"),
        "cached_tokens_a": state.get("cached_tokens_a"),
        "prompt_tokens_b": state.get("prompt_tokens_b"),
        "cached_tokens_b": state.get("cached_tokens_b"),
        "hit_rate_b": state.get("hit_rate_b"),
        "verdict": state.get("verdict"),
    }
    js_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_file.write_text(
        "\n".join([
            f"# cache witness — {state.get('started_utc')}",
            "",
            f"- strike A: prompt={state.get('prompt_tokens_a')} cached={state.get('cached_tokens_a')}",
            f"- strike B: prompt={state.get('prompt_tokens_b')} cached={state.get('cached_tokens_b')}",
            f"- hit_rate(B): {(state.get('hit_rate_b') or 0) * 100:.1f}%",
            f"- verdict: **{state.get('verdict')}**",
            "",
        ]),
        encoding="utf-8",
    )
    return {"report_path": str(md_file)}


def build_graph() -> Any:
    g = StateGraph(CacheWitnessState)
    g.add_node("intake", intake_node)
    g.add_node("strike_one", strike_one_node)
    g.add_node("strike_two", strike_two_node)
    g.add_node("verdict", verdict_node)
    g.add_node("report", report_node)
    g.set_entry_point("intake")
    g.add_edge("intake", "strike_one")
    g.add_edge("strike_one", "strike_two")
    g.add_edge("strike_two", "verdict")
    g.add_edge("verdict", "report")
    g.add_edge("report", END)
    return g.compile()


if __name__ == "__main__":
    graph = build_graph()
    out = graph.invoke({})
    print(
        f"verdict={out.get('verdict')} hit_rate={(out.get('hit_rate_b') or 0) * 100:.1f}% "
        f"strike_a_cached={out.get('cached_tokens_a')} strike_b_cached={out.get('cached_tokens_b')} "
        f"report={out.get('report_path')}"
    )
    raise SystemExit(0 if out.get("cached_tokens_b") is not None else 1)
