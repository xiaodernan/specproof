"""insight_advice_graph.py — witness the /insight AI 解读 lane, struck live.

One knock against the advice lane with the same allowlisted aggregate packet
the Insight Deck itself renders (deterministic synthetic cohort re-derived
bit-for-bit from apps/web/src/pages/insight.copy.ts). Verdicts:

    ANSWERED    the model returned nonempty advice + usage through the lane
    UNAVAILABLE the lane failed honestly (503 semantics; nothing synthesized)

This graph is NOT a judge and does not grade the advice — linting content is
court territory and court is not invited anywhere near this lane. It only
reports: could the lane answer, and what did it cost.

Pattern: intake -> strike -> verdict -> report -> END

Usage:

    HTTPS_PROXY=http://127.0.0.1:7897 python agent/graphs/insight_advice_graph.py

Writes docs/evidence/insight-advice-witness.json + docs/evidence/insight-advice-witness.md.
"""
from __future__ import annotations

import asyncio
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

from api.insight_advice import (  # noqa: E402
    InsightAdviceError,
    build_insight_packet,
    fingerprint,
    generate_insight_advice,
    sanitize_stats,
)


class AdviceWitnessState(TypedDict, total=False):
    started_utc: str
    packet_chars: int
    fingerprint: str
    model: str
    latency_ms: int
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cached_tokens: int
    advice_chars: int
    verdict: str
    report_path: str
    notes: str


def _synthetic_cohort() -> dict[str, Any]:
    """The same deterministic cohort the browser renders; bit-for-bit with
    scripts/live_insight_strike.py. Zeros here are CLI zeros, honest zeros."""
    import math

    def imul(a: int, b: int) -> int:
        a &= 0xFFFFFFFF
        b &= 0xFFFFFFFF
        p = (a * b) & 0xFFFFFFFF
        return p - 0x100000000 if p & 0x80000000 else p

    def mulberry32(seed: int) -> list[float]:
        a = seed & 0xFFFFFFFF
        out: list[float] = []
        while len(out) < 28:
            a = (a + 0x6D2B79F5) & 0xFFFFFFFF
            t = imul(a ^ (a >> 15), 1 | a)
            t = (imul(t ^ (t >> 7), 61 | t) ^ t) & 0xFFFFFFFF
            out.append((t ^ (t >> 14)) / 4294967296)
        return out

    def least_squares(y: list[int]) -> tuple[float, float, float]:
        n = len(y)
        xs = list(range(n))
        mx = sum(xs) / n
        my = sum(y) / n
        sxx = sum((x - mx) ** 2 for x in xs)
        sxy = sum((x - mx) * (v - my) for x, v in zip(xs, y, strict=False))
        syy = sum((v - my) ** 2 for v in y)
        slope = 0.0 if sxx == 0 else sxy / sxx
        intercept = my - slope * mx
        r2 = 1.0 if syy == 0 else (sxy * sxy) / (sxx * syy)
        return slope, intercept, r2

    rand = iter(mulberry32(20261115))
    sessions = []
    for d in range(28):
        weekday = d % 7
        weekend_penalty = 0.72 if weekday >= 5 else 1
        wave = 1 + 0.18 * math.sin((d / 28) * math.pi * 2.2)
        noise = 0.78 + next(rand) * 0.46
        sessions.append(math.floor(340 * weekend_penalty * wave * noise + 0.5))
    last14 = sessions[-14:]
    slope, _, r2 = least_squares(last14)

    funnel = [
        {"k": "visit", "v": 240}, {"k": "tour", "v": 201}, {"k": "tourDone", "v": 113},
        {"k": "first", "v": 84}, {"k": "accepted", "v": 41},
    ]
    features = [
        {"k": "epic", "v": 156}, {"k": "atlas", "v": 141}, {"k": "lexicon", "v": 128},
        {"k": "drill", "v": 110}, {"k": "worldbook", "v": 97}, {"k": "gestures", "v": 76},
        {"k": "nightwatch", "v": 52}, {"k": "gazette", "v": 48}, {"k": "manual", "v": 33},
        {"k": "census", "v": 21},
    ]
    personas = [
        {"k": "skeptic", "v": 58}, {"k": "firsttimer", "v": 64}, {"k": "tourist", "v": 61},
        {"k": "archivist", "v": 27}, {"k": "speedrun", "v": 18}, {"k": "nightowl", "v": 12},
    ]
    return {
        "population": 240,
        "slope_per_day": slope,
        "r2": r2,
        "sessions_today": sessions[-1],
        "median_dwell_min": 6.4,
        "drill_pass_rate": 0.62,
        "tour_completion_rate": 113 / 201,
        "funnel": funnel,
        "features": features,
        "personas": personas,
        "heat_taps_total": 0,
        "heat_rage_count": 0,
        "onboarding_routes": 0,
    }


def intake_node(state: AdviceWitnessState) -> AdviceWitnessState:
    stats = sanitize_stats(_synthetic_cohort())
    return {
        "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "packet_chars": len(build_insight_packet(stats)),
        "fingerprint": fingerprint(stats)[:16],
    }


def strike_node(state: AdviceWitnessState) -> AdviceWitnessState:
    try:
        out = asyncio.run(generate_insight_advice(_synthetic_cohort()))
    except InsightAdviceError:
        return {"verdict": "UNAVAILABLE"}
    usage = out.get("usage") or {}

    def _u(key: str) -> int:
        value = usage.get(key)
        return int(value) if isinstance(value, (int, float)) else 0

    return {
        "model": out.get("model") or "",
        "latency_ms": int(out.get("model_latency_ms") or 0),
        "prompt_tokens": _u("prompt_tokens"),
        "completion_tokens": _u("completion_tokens"),
        "reasoning_tokens": _u("reasoning_tokens"),
        "cached_tokens": _u("prompt_cache_hit_tokens"),
        "advice_chars": len(out.get("advice") or ""),
    }


def verdict_node(state: AdviceWitnessState) -> AdviceWitnessState:
    if state.get("verdict") == "UNAVAILABLE":
        return state
    if (state.get("advice_chars") or 0) > 0 and state.get("latency_ms"):
        return {"verdict": "ANSWERED"}
    return {"verdict": "UNAVAILABLE"}


def report_node(state: AdviceWitnessState) -> AdviceWitnessState:
    out_dir = Path(os.environ.get("SPECPROOF_INSIGHT_WITNESS_OUT", "docs/evidence"))
    out_dir.mkdir(parents=True, exist_ok=True)
    json_file = out_dir / "insight-advice-witness.json"
    md_file = out_dir / "insight-advice-witness.md"
    payload = {
        "version": 1,
        "started_utc": state.get("started_utc"),
        "packet_chars": state.get("packet_chars"),
        "fingerprint": state.get("fingerprint"),
        "model": state.get("model"),
        "latency_ms": state.get("latency_ms"),
        "prompt_tokens": state.get("prompt_tokens"),
        "completion_tokens": state.get("completion_tokens"),
        "reasoning_tokens": state.get("reasoning_tokens"),
        "cached_tokens": state.get("cached_tokens"),
        "advice_chars": state.get("advice_chars"),
        "verdict": state.get("verdict"),
    }
    json_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_file.write_text(
        "\n".join([
            f"# insight advice witness — {state.get('started_utc')}",
            "",
            f"- packet: {state.get('packet_chars')} chars · fingerprint {state.get('fingerprint')}",
            f"- model: {state.get('model')} · latency {state.get('latency_ms')} ms",
            f"- usage: prompt {state.get('prompt_tokens')} · completion {state.get('completion_tokens')} · reasoning {state.get('reasoning_tokens')} · cached {state.get('cached_tokens')}",
            f"- advice_chars: {state.get('advice_chars')}",
            f"- verdict: **{state.get('verdict')}**",
            "",
        ]),
        encoding="utf-8",
    )
    return {"report_path": str(md_file)}


def build_graph() -> Any:
    g = StateGraph(AdviceWitnessState)
    g.add_node("intake", intake_node)
    g.add_node("strike", strike_node)
    g.add_node("verdict", verdict_node)
    g.add_node("report", report_node)
    g.set_entry_point("intake")
    g.add_edge("intake", "strike")
    g.add_edge("strike", "verdict")
    g.add_edge("verdict", "report")
    g.add_edge("report", END)
    return g.compile()


if __name__ == "__main__":
    graph = build_graph()
    out = graph.invoke({})
    print(
        f"verdict={out.get('verdict')} latency_ms={out.get('latency_ms')} "
        f"packet_chars={out.get('packet_chars')} advice_chars={out.get('advice_chars')} "
        f"model={out.get('model')} report={out.get('report_path')}"
    )
    raise SystemExit(0 if out.get("verdict") == "ANSWERED" else 1)
