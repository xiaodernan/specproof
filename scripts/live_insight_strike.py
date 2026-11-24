"""live_insight_strike.py — strike the Insight AI advice lane live, once.

Re-derives the deterministic synthetic cohort bit-for-bit from
apps/web/src/pages/insight.copy.ts (mulberry32 · last-14 least-squares),
feeds it through the real allowlist sanitizer in api/insight_advice.py, and
puts one REAL call to the aizzz lane (through the local Clash Verge proxy)
on the record. First strike: 2026-11-16 · gpt-6.1-terra · ~17 s · the model
cited the packet's own drop-offs and refused to extrapolate where the
packet said nothing ("本包数据不足以判断"). Not committed anywhere.
Run: python scripts/live_insight_strike.py  # direct; set proxies in the real env only if needed
"""
import asyncio
import json
import math
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.getcwd())


def imul(a, b):
    a &= 0xFFFFFFFF
    b &= 0xFFFFFFFF
    p = (a * b) & 0xFFFFFFFF
    return p - 0x100000000 if p & 0x80000000 else p


def mulberry32(seed):
    a = seed & 0xFFFFFFFF
    out = []
    while len(out) < 28:
        a = (a + 0x6D2B79F5) & 0xFFFFFFFF
        t = imul(a ^ (a >> 15), 1 | a)
        t = (imul(t ^ (t >> 7), 61 | t) ^ t) & 0xFFFFFFFF
        out.append((t ^ (t >> 14)) / 4294967296)
    return out


def least_squares(y):
    n = len(y)
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(y) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (v - my) for x, v in zip(xs, y, strict=False))
    syy = sum((v - my) ** 2 for v in y)
    slope = 0 if sxx == 0 else sxy / sxx
    intercept = my - slope * mx
    r2 = 1 if syy == 0 else (sxy * sxy) / (sxx * syy)
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
slope, intercept, r2 = least_squares(last14)
sessions_today = sessions[-1]

population = 240
tour_started, tour_completed, first_verification, accepted = 201, 113, 84, 41

funnel = [
    {"k": "visit", "v": population},
    {"k": "tour", "v": tour_started},
    {"k": "tourDone", "v": tour_completed},
    {"k": "first", "v": first_verification},
    {"k": "accepted", "v": accepted},
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

stats = {
    "population": population,
    "slope_per_day": slope,
    "r2": r2,
    "sessions_today": sessions_today,
    "median_dwell_min": 6.4,
    "drill_pass_rate": 0.62,
    "tour_completion_rate": tour_completed / tour_started,
    "funnel": funnel,
    "features": features,
    "personas": personas,
    # the CLI battlefield has no browser heat; zeros here are the real zeros
    "heat_taps_total": 0,
    "heat_rage_count": 0,
    "onboarding_routes": 0,
}

from api.insight_advice import (  # noqa: E402
    build_insight_packet,
    fingerprint,
    generate_insight_advice,
    sanitize_stats,
)

sane = sanitize_stats(stats)
print("scalars kept:", sorted(k for k in sane if not isinstance(sane[k], list)))
print("sessions_today:", sessions_today, "slope/day:", round(slope, 3), "r2:", round(r2, 4))
print("packet chars:", len(build_insight_packet(stats)))
print("fingerprint:", fingerprint(stats)[:16])

out = asyncio.run(generate_insight_advice(stats))
print("model:", out["model"])
print("latency_ms:", out["model_latency_ms"])
print("usage:", json.dumps(out["usage"], ensure_ascii=False))
print("packet_chars:", out["evidence_packet_chars"])
print("=== ADVICE (AI 解读, not a verdict) ===")
print(out["advice"])
