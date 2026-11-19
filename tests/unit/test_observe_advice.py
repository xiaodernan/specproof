"""The Observatory lane — deterministic cohort parity, fingerprint caching,
fail-closed honesty. Nothing in this module touches the network."""

from __future__ import annotations

import json

import pytest

from api.observe_advice import (
    ObserveAdviceError,
    build_observe_packet,
    fingerprint,
    generate_observe_advice,
)
from api.synthetic_cohort import build_sessions_per_day, cohort
from providers.base import LLMResponse

# Frozen from the shipped TS buildInsight() so both languages tell one story.
PINNED_SESSIONS = [308, 408, 303, 327, 358, 247, 357, 488, 452, 346, 468, 419,
                   260, 291, 277, 350, 265, 296, 301, 200, 242, 227, 230, 362,
                   261, 288, 201, 232]
PINNED_FORECAST = [236, 231, 227, 223, 219, 215, 211]
PINNED_FUNNEL = [240, 201, 113, 84, 41]


def test_sessions_per_day_are_deterministic() -> None:
    assert build_sessions_per_day() == PINNED_SESSIONS


def test_cohort_is_self_consistent() -> None:
    c = cohort()
    assert c["population"] == 240
    assert c["sessions_today"] == 232 == PINNED_SESSIONS[-1]
    assert c["predicted_next_7"] == PINNED_FORECAST
    assert c["daily_slope_per_day"] == pytest.approx(-4.136263736, abs=1e-9)
    assert c["r2"] == pytest.approx(0.121051606, abs=1e-9)
    assert [s["count"] for s in c["funnel"]] == PINNED_FUNNEL
    assert sum(p["count"] for p in c["personas"]) == 240
    assert sum(f["users"] for f in c["features"]) >= 1  # adoptions are subset of population
    assert -4.14 < c["daily_slope_per_day"] < -4.13
    assert 0.12 < c["r2"] < 0.13


def test_fingerprint_is_stable_and_locale_sensitive() -> None:
    assert fingerprint("zh") == fingerprint("zh")
    assert fingerprint("zh") != fingerprint("en")
    assert len(fingerprint("zh")) == 64


def test_packet_is_bounded_synthetic_only_and_locale_aware() -> None:
    for locale in ("zh", "en"):
        text = build_observe_packet(locale)
        assert len(text) <= 2_000
        packet = json.loads(text)
        assert packet["synthetic"] is True
        assert packet["locale"] == locale
        # no keys beyond the public aggregates — nothing extra smuggled in
        assert set(packet) <= {
            "locale", "synthetic", "seed", "population", "sessions_today",
            "sessions_per_day", "predicted_next_7", "daily_slope_per_day",
            "r2", "tour_completion_rate", "drill_pass_rate",
            "median_dwell_min", "funnel", "personas", "features", "truncated",
        }


class _FakeProvider:
    def __init__(self, **_: object) -> None:
        pass

    async def chat(self, _messages, timeout: float | None = None, opts: dict | None = None):  # noqa: ANN001
        return LLMResponse(
            content="LIVE-READING: flat, mildly cooling, r² = 0.12 — not a verdict.",
            usage={"prompt_tokens": 720, "completion_tokens": 61},
            model="gpt-6.1-terra",
        )

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_live_answer_path_returns_protocol_object() -> None:
    result = await generate_observe_advice(
        "zh", provider_factory=lambda timeout, max_retries: _FakeProvider(),
    )
    assert result["advice"].startswith("LIVE-READING")
    assert result["model"] == "gpt-6.1-terra"
    assert result["model_latency_ms"] >= 0
    assert result["evidence_packet_chars"] > 100


@pytest.mark.asyncio
async def test_provider_failure_is_one_honest_error() -> None:
    def boom(*_: object, **__: object):  # noqa: ANN001
        raise RuntimeError("provider unreachable")

    with pytest.raises(ObserveAdviceError):
        await generate_observe_advice("en", provider_factory=boom)


@pytest.mark.asyncio
async def test_empty_answer_is_one_honest_error() -> None:
    class _EmptyProvider(_FakeProvider):
        async def chat(self, _messages, timeout: float | None = None, opts: dict | None = None):  # noqa: ANN001
            return LLMResponse(content="   ", model="gpt-6.1-terra")

    with pytest.raises(ObserveAdviceError):
        await generate_observe_advice(
            "zh", provider_factory=lambda timeout, max_retries: _EmptyProvider(),
        )
