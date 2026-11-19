"""Lane cache probe — strike the six cacheable lanes twice each, live.

Every strike runs the real lane code path (``generate_*``), not a mock.
Recorded per strike: wall seconds, outcome, and the usage dict the gateway
returned. Nothing here is graded or beautified — when the gateway answers
0 cached tokens, that is the number in the evidence file.

Re-running merges into one evidence file: results are keyed by
(lane, strike) and the newer row replaces the older one.

Usage:
  python -X utf8 scripts/lane_cache_probe.py [lane ...]
  lanes: observe insight ai_summary dig runbook ask_the_book (default: all six)
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs" / "evidence" / "lane-cache-probe-2026-11-18.json"

# A labeled probe packet — the schema marker keeps the probe honest without
# minting any verdict-like literal ("verdict" stays OUT of this script).
PROBE_SUMMARY = {
    "probe_marker": "LANE-CACHE-PROBE",
    "contracts_total": 1,
    "matrix_passed": 1,
    "matrix_failed": 0,
    "matrix_unverified": 0,
    "matrix_results": [
        {
            "contract_id": "PROBE-1", "result": "PASS",
            "severity": "low", "evidence_type": "cache-probe",
        }
    ],
    "coverage_reason": "lane cache probe — not an acceptance verdict",
    "retrieval_note": "synthetic probe input, byte-identical across strikes",
}

PROBE_QUESTION = "In one sentence: what is this repository?"


async def _strike(lane: str, i: int, call) -> dict:
    t0 = time.perf_counter()
    try:
        result = await call()
        agents = result.get("agents") or []
        row = {"lane": lane, "strike": i, "outcome": "ok",
               "elapsed_s": round(time.perf_counter() - t0, 2)}
        if agents:
            row["agents"] = [{
                "name": a.get("name"),
                "outcome": a.get("outcome"),
                "tokens": a.get("tokens"),
                "usage": a.get("usage") or {},
            } for a in agents]
        else:
            row["usage"] = result.get("usage") or {}
        return row
    except Exception as exc:
        return {"lane": lane, "strike": i, "outcome": "error",
                "elapsed_s": round(time.perf_counter() - t0, 2),
                "error": f"{type(exc).__name__}: {exc}"}


async def strike_observe(n: int) -> list[dict]:
    from api.observe_advice import generate_observe_advice
    return [
        await _strike("observe", i, lambda: generate_observe_advice("zh"))
        for i in range(1, n + 1)
    ]


async def strike_insight(n: int) -> list[dict]:
    from api.insight_advice import generate_insight_advice
    stats_path = ROOT / "apps" / "web" / "src" / "pages" / "repoStats.json"
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    return [
        await _strike("insight", i, lambda: generate_insight_advice(stats))
        for i in range(1, n + 1)
    ]


async def strike_ai_summary(n: int) -> list[dict]:
    from api.ai_summary import generate_ai_summary
    return [
        await _strike("ai_summary", i, lambda: generate_ai_summary(PROBE_SUMMARY))
        for i in range(1, n + 1)
    ]


async def strike_dig(n: int) -> list[dict]:
    from craft.investigators import investigate
    return [
        await _strike("dig", i, lambda: investigate(ROOT, PROBE_QUESTION))
        for i in range(1, n + 1)
    ]


async def strike_runbook(n: int) -> list[dict]:
    from api.runbook_triage import generate_triage
    return [
        await _strike("runbook", i, lambda: generate_triage("SpecproofApiHigh5xxRate"))
        for i in range(1, n + 1)
    ]


async def strike_ask_the_book(n: int) -> list[dict]:
    from api.worldbook_ask import generate_ask_answer

    async def call() -> dict:
        result = await generate_ask_answer(
            "世界书从哪一卷开始？", "zh",
        )
        return {
            "agents": [],
            "usage": result.get("usage") or {},
        }

    return [await _strike("ask_the_book", i, call) for i in range(1, n + 1)]


LANES = {
    "observe": strike_observe,
    "insight": strike_insight,
    "ai_summary": strike_ai_summary,
    "dig": strike_dig,
    "runbook": strike_runbook,
    "ask_the_book": strike_ask_the_book,
}

PROMPT_CACHE_KEYS = {
    # the nine sticky per-lane keys used by the product lanes; the probe
    # strikes only the six anonymous lanes in LANES above, but this registry
    # documents the full set for the evidence file. admin/operator lanes
    # (next_step_advice / stress_digest) and exhibit_copilot share the same
    # one-key-per-lane discipline; they are not personally struck here.
    "observe": "specproof-observe-advice",
    "insight": "specproof-insight-advice",
    "ai_summary": "specproof-ai-summary",
    "dig": "specproof-dig",
    "runbook": "specproof-runbook",
    "ask_the_book": "specproof-worldbook-ask",
    "exhibit_copilot": "specproof-exhibit-copilot",
    "next_step_advice": "specproof-next-step-advice",
    "stress_digest": "specproof-stress-digest",
}


def _merge(existing: dict, fresh_rows: list[dict]) -> dict:
    keyed = {(r["lane"], r["strike"]): r for r in existing.get("results", [])}
    for row in fresh_rows:
        keyed[(row["lane"], row["strike"])] = row
    return {**existing, "results": sorted(keyed.values(), key=lambda r: (r["lane"], r["strike"]))}


async def main() -> int:
    picked = sys.argv[1:] or list(LANES)
    unknown = [lane for lane in picked if lane not in LANES]
    if unknown:
        print(f"unknown lanes: {unknown}", file=sys.stderr)
        return 2
    results: list[dict] = []
    for lane in picked:
        print(f"--- {lane} (2 strikes) ---", flush=True)
        rows = await LANES[lane](2)
        results.extend(rows)
        for row in rows:
            usage = row.get("usage") or {}
            agents = row.get("agents") or []
            if agents:
                hits = sum(
                    int((a.get("usage") or {}).get("prompt_cache_hit_tokens") or 0)
                    for a in agents)
                print(f"{lane} #{row['strike']} {row['outcome']} {row.get('elapsed_s')}s "
                      f"agents={len(agents)} cache_hit_tokens={hits}", flush=True)
            else:
                print(f"{lane} #{row['strike']} {row['outcome']} {row.get('elapsed_s')}s "
                      f"prompt={usage.get('prompt_tokens')} "
                      f"cached={usage.get('prompt_cache_hit_tokens')} "
                      f"reasoning={usage.get('reasoning_tokens')}", flush=True)
    if EVIDENCE.is_file():
        try:
            prior = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        except Exception:
            prior = {}
    else:
        prior = {}
    evidence = _merge(prior, results)
    from providers.config import load_model_config  # noqa: E402

    evidence.update({
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": load_model_config().get("model") or "unknown",
        "protocol": "responses",
        "prompt_cache_key_per_lane": PROMPT_CACHE_KEYS,
        "note": "live probes; the two strikes per lane are byte-identical on the prefix;"
        " no verdicts minted; numbers recorded as returned",
    })
    EVIDENCE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {EVIDENCE}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
