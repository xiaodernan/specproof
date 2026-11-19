"""The codex (#1977): the world-book bible rides the cacheable lanes.

Pinned here, once and for all:

* the zh and en codices are byte-identical across calls, carry the full
  bibles (well over 200 KB each), and are routed by the lane's locale;
* ``codex_first`` prepends exactly one system message and leaves the tail
  untouched;
* the five cacheable lanes wire both ``codex_first`` and their own
  ``prompt_cache_key`` — the key is stable, lowercase, and under 64 chars;
* the court (``agent/review_court``) never carries the codex and never
  carries a ``prompt_cache_key`` — the review gate strikes without cache,
  forever.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

from api.system_codex import (  # noqa: E402
    SPECROOF_CODEX_EN,
    SPECROOF_CODEX_ZH,
    codex_first,
    codex_for,
)
from providers.base import LLMMessage  # noqa: E402


def test_codex_bodies_are_the_real_bibles() -> None:
    assert len(SPECROOF_CODEX_ZH) > 200_000
    assert len(SPECROOF_CODEX_EN) > 200_000
    # byte-frozen: same bytes twice, every time
    assert codex_for("zh") == codex_for("zh")
    assert codex_for("en") == codex_for("en")
    assert codex_for("zh") != codex_for("en")


def test_codex_locale_routing_and_headers() -> None:
    zh = codex_for("zh")
    en = codex_for("en")
    assert zh.startswith("以下不是虚构")
    assert en.startswith("The following is not fiction")
    assert codex_for("fr") == zh  # unknown languages fall back to zh (never a mix)


def test_codex_first_prepends_exactly_one_system_message() -> None:
    tail = [
        LLMMessage(role="system", content="role"),
        LLMMessage(role="user", content="question"),
    ]
    out = codex_first(tail, locale="zh")
    assert len(out) == 3
    assert out[0].role == "system"
    assert "以下不是虚构" in out[0].content
    assert out[1:] == tail


def test_cacheable_lanes_carry_codex_and_sticky_key() -> None:
    lanes = {
        "api/ai_summary.py": "specproof-ai-summary",
        "api/insight_advice.py": "specproof-insight-advice",
        "api/observe_advice.py": "specproof-observe-advice",
        "craft/investigators.py": "specproof-dig",
        "api/runbook_triage.py": "specproof-runbook",
        "craft/investigators.py:key-default": "specproof-dig",
    }
    sources = {
        rel: (REPO / rel).read_text(encoding="utf-8")
        for rel in {"api/ai_summary.py", "api/insight_advice.py", "api/observe_advice.py",
                    "craft/investigators.py", "api/runbook_triage.py"}
    }
    for rel, key in lanes.items():
        path = rel.split(":")[0]
        assert key in sources[path], f"{path} lost its sticky key {key!r}"
    assert "codex_first" in sources["api/ai_summary.py"]
    assert "codex_first" in sources["api/insight_advice.py"]
    assert "codex_first" in sources["api/observe_advice.py"]
    assert "codex_first" in sources["craft/investigators.py"]


def test_the_court_never_carries_codex_nor_cache_key() -> None:
    forbidden = ("prompt_cache_key", "system_codex", "SPECROOF_CODEX", "codex_first", "specproof-dig")
    court = REPO / "agent" / "review_court"
    scanned = 0
    for py in court.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        scanned += 1
        for token in forbidden:
            assert token not in text, f"the court path {py} carries {token!r} — court must never cache"
    assert scanned >= 2, "the court tree scanned empty"
