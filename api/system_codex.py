"""The codex — a byte-identical, frozen-sandwich prefix for the cacheable lanes.

Why this file exists: the previous covenant (``api/system_covenant.py``) covers
the law. The codex covers the **story** — the entire world-book bible put into
the cache axis by every cacheable lane. This gives the aizzz gateway
(which honors ``prompt_cache_key``) a long, byte-identical prefix to charge
against, so repeated strikes on the same lane share the cached prefix instead
of re-reading the whole repo bible on every turn.

The body is read ONCE at import and is byte-frozen — any edit invalidates all
downstream cache entries. When it must change (a new world volume lands), the
edit is deliberate, lands in the same commit as a covenant-prefix bump, and
re-strikes the probes.

The court (``agent/review_court``) never carries the codex and never carries a
``prompt_cache_key`` — pinned by ``tests/unit/test_system_codex.py``.
"""
from __future__ import annotations

from pathlib import Path

from api.system_covenant import covenant_prefix
from providers.base import LLMMessage

_ROOT = Path(__file__).resolve().parents[1]


def _read_guard(path: str) -> str:
    p = _ROOT / path
    if not p.is_file():
        raise RuntimeError(f"system codex missing: {p}")
    return p.read_text(encoding="utf-8")


SPECROOF_CODEX_ZH: str = _read_guard("docs/world/SPECROOF_WORLD.md").strip()
SPECROOF_CODEX_EN: str = _read_guard("docs/world/EN/SPECROOF_WORLD_EN.md").strip()

_HEADER_ZH = (
    "以下不是虚构——这是本仓库的书。每一卷都是真实事件落下的：\n"
    "真 commit、真 exhibit、真敲门、真 court。读一遍即可。它知道的法就是它执行的法。"
)

_HEADER_EN = (
    "The following is not fiction — this is this repository's own book. "
    "Every volume was struck by real commits, real exhibits, real gates, "
    "real courts. Read it once. The laws it knows are the laws it enforces."
)


def codex_for(locale: str) -> str:
    """The byte-frozen codex for a lane language (zh by default)."""
    if locale == "en":
        return _HEADER_EN + "\n\n" + SPECROOF_CODEX_EN
    return _HEADER_ZH + "\n\n" + SPECROOF_CODEX_ZH


def bilingual_packet_messages(
    locale: str, packet: str, *, system_zh: str, system_en: str
) -> list[LLMMessage]:
    """One codex→covenant→role sandwich for the bilingual packet lanes.

    next-step advice and stress digest had byte-identical ``_prompt`` bodies;
    only their two system strings differed. Those strings are passed in here,
    so the sandwich order and the packet labels stay one decision.
    """
    lang = "en" if locale == "en" else "zh"
    system = system_en if lang == "en" else system_zh
    return codex_first(covenant_prefix([
        LLMMessage(role="system", content=system),
        LLMMessage(
            role="user",
            content=("数据包（JSON）：\n" if lang == "zh" else "Packet (JSON):\n") + packet,
        ),
    ]), lang)


def codex_first(messages: list[LLMMessage], locale: str = "zh") -> list[LLMMessage]:
    """Prepend the codex as one system message; the covenant rides behind it.

    The lane call sites already carry ``covenant_prefix([...])`` — this layer
    puts the ~400 KB bible in front of that, so all cacheable lanes share the
    exact same byte prefix in identical order: codex → covenant → role.
    """
    return [LLMMessage(role="system", content=codex_for(locale)), *messages]
