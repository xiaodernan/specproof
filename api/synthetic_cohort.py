"""The synthetic calibration cohort — the Python twin of the Observatory's
``buildInsight()`` in the web bundle.

Why this file exists: the public ``/observe`` page renders its aggregates from
``apps/web/src/pages/insight.copy.ts`` in the browser. The server must be able
to compute the very same aggregates on its own — no client-supplied numbers
are trusted anywhere — so the model reads the same shapes either way.

The algorithm is a line-for-line port of the TS original: mulberry32
(seed 20261115) + least-squares over the last 14 days. Both sides are
deterministic; ``tests/unit/test_synthetic_cohort.py`` pins the parity.
Nothing here is real user data — it never was, and it cannot become real.
"""
from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

SEED = 20261115
_POPULATION = 240
_TOUR_STARTED = 201
_TOUR_COMPLETED = 113
_FIRST_VERIFICATION = 84
_ACCEPTED = 41
_DRILL_PASS_RATE = 0.62
_MEDIAN_DWELL_MIN = 6.4


def _to_int32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 0x100000000 if value >= 0x80000000 else value


def _imul(x: int, y: int) -> int:
    return _to_int32(_to_int32(x) * _to_int32(y))


def _ushr(x: int, bits: int) -> int:
    return (x & 0xFFFFFFFF) >> bits


def _mulberry32(seed: int) -> Iterator[float]:
    a = _to_int32(seed)
    while True:
        a = _to_int32(a + 0x6D2B79F5)
        t = _imul(a ^ _ushr(a, 15), 1 | a)
        t = _to_int32(t + _imul(t ^ _ushr(t, 7), 61 | t)) ^ t
        yield ((_to_int32(t ^ _ushr(t, 14))) & 0xFFFFFFFF) / 4294967296


def _js_round(x: float) -> int:
    # JS Math.round for positive x == floor(x + 0.5); Python round() is banker's.
    return math.floor(x + 0.5)


def _least_squares(series: list[float]) -> dict[str, float]:
    n = len(series)
    mean_x = (n - 1) / 2
    mean_y = sum(series) / n
    sxx = sum((i - mean_x) ** 2 for i in range(n))
    sxy = sum((i - mean_x) * (series[i] - mean_y) for i in range(n))
    syy = sum((v - mean_y) ** 2 for v in series)
    slope = sxx and sxy / sxx or 0.0
    intercept = mean_y - slope * mean_x
    r2 = 1.0 if syy == 0 else (sxy * sxy) / (sxx * syy)
    return {"slope": slope, "intercept": intercept, "r2": r2}


def build_sessions_per_day() -> list[int]:
    rand = _mulberry32(SEED)
    sessions: list[int] = []
    for d in range(28):
        weekday = d % 7
        weekend_penalty = 0.72 if weekday >= 5 else 1.0
        wave = 1 + 0.18 * math.sin((d / 28) * math.pi * 2.2)
        noise = 0.78 + next(rand) * 0.46
        sessions.append(_js_round(340 * weekend_penalty * wave * noise))
    return sessions


def cohort() -> dict[str, Any]:
    sessions = build_sessions_per_day()
    last14 = sessions[-14:]
    fit = _least_squares([float(v) for v in last14])
    slope, intercept, r2 = fit["slope"], fit["intercept"], fit["r2"]
    predicted_next_7 = [
        max(0, _js_round(intercept + slope * (len(last14) + k))) for k in range(7)
    ]
    funnel = [
        {"key": "visit", "zh": "进入工作台", "en": "Opened the workspace", "count": _POPULATION},
        {"key": "tour", "zh": "开始巡览（六盖印）",
         "en": "Started the Grand Tour", "count": _TOUR_STARTED},
        {"key": "tourDone", "zh": "通关巡览", "en": "Completed the tour", "count": _TOUR_COMPLETED},
        {"key": "first", "zh": "发起首次验收",
         "en": "Ran the first verification", "count": _FIRST_VERIFICATION},
        {"key": "accepted", "zh": "获得一枚验讫印",
         "en": "Landed one sealed ACCEPT", "count": _ACCEPTED},
    ]
    features = [
        {"key": "epic", "zh": "史诗·创世记", "en": "Epic · Genesis", "users": 156},
        {"key": "atlas", "zh": "世界舆图", "en": "The Atlas", "users": 141},
        {"key": "lexicon", "zh": "铁证词典", "en": "Iron Lexicon", "users": 128},
        {"key": "drill", "zh": "验收快问", "en": "Verify Drill", "users": 110},
        {"key": "worldbook", "zh": "世界书", "en": "World Book", "users": 97},
        {"key": "gestures", "zh": "十四式", "en": "Fourteen Gestures", "users": 76},
        {"key": "nightwatch", "zh": "巡夜·子时之后", "en": "The Night Watch", "users": 52},
        {"key": "gazette", "zh": "铁证晨报", "en": "The Gazette", "users": 48},
        {"key": "manual", "zh": "袖中手札", "en": "Pocket Card", "users": 33},
        {"key": "census", "zh": "铁样寨地", "en": "Iron Census", "users": 21},
    ]
    personas = [
        {"key": "skeptic", "zh": "怀疑论验收官", "en": "The Skeptic", "count": 58},
        {"key": "firsttimer", "zh": "初出茅庐的工程师", "en": "The First-timer", "count": 64},
        {"key": "tourist", "zh": "路过看热闹的游客", "en": "The Tourist", "count": 61},
        {"key": "archivist", "zh": "铁证考古学家", "en": "The Archivist", "count": 27},
        {"key": "speedrun", "zh": "追印章的效率主义者", "en": "The Speedrunner", "count": 18},
        {"key": "nightowl", "zh": "子时守夜人", "en": "The Night Watch", "count": 12},
    ]
    return {
        "population": _POPULATION,
        "sessions_today": sessions[-1],
        "sessions_per_day": sessions,
        "predicted_next_7": predicted_next_7,
        "daily_slope_per_day": slope,
        "r2": r2,
        "funnel": funnel,
        "features": features,
        "personas": personas,
        "median_dwell_min": _MEDIAN_DWELL_MIN,
        "drill_pass_rate": _DRILL_PASS_RATE,
        "tour_completion_rate": _TOUR_COMPLETED / _TOUR_STARTED,
        "seed": SEED,
    }
