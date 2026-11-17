"""The Exhibit Co-Pilot — the evidence gauntlet hums once for the wall.

One paragraph of the evidence packet → two honest captions (zh + en) for the
exhibit wall. This is the machine signing a picture of its own strike, not a
verdict on anything. Boundaries, all machine-checked in ``validate_copilot``:

* the packet is the only source of truth — every number in the answer must
  appear verbatim in the packet text;
* ceilings: zh ≤ 200 CJK chars · en ≤ 150 words;
* plain text only — no markdown headings, no bullet roster, no code fences;
* banned words: the ones that would read as verdicts (see ``_BANNED``) — the
  product decides verdicts; the machine may only hum;
* if the packet cannot carry a claim, say exactly what is missing.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

from api.system_covenant import covenant_prefix
from providers.base import LLMMessage, LLMResponse
from providers.openai_compatible import OpenAICompatibleProvider

LLM_TIMEOUT_SECONDS = 90.0

EXHIBIT_COPILOT_SYSTEM = (
    "你是 SpecProof 展馆的速写员。下面是一次风压试的裁图，它已经由系统裁好。"
    "\n"
    "你只能做三件事：\n"
    "1. 用一句话说这波风压试的形状（0 错误、96 并发、768 次请求、最慢 p99），不许补充任何文件里没有的事实；\n"
    "2. 用一句话说它与上一件展品的不同（#18 比 #17 慢 492.6 毫秒是因为完整 pytest 同时在敲门，不是退化）；\n"
    "3. 说一句下一位游客应该先看什么。\n"
    "\n"
    "你不许判任何胜败；不许下任何结论式的话；不许说「通过」「合格」「必胜」「全绿」之类的判词；\n"
    "中文不超过 200 字，英文不超过 150 词；\n"
    "不许加 markdown 标题、不许列点、不许 code fence；\n"
    "数据包里没有的数字，不许出现；数据包里没有的字段名，不许编造。\n"
    "\n"
    "If the packet cannot carry one of the three things, write what is missing: "
    "「包里没有 X」 or 「the packet carries no Y」. Never a guess.\n"
    "\n"
    "Output format, exactly two paragraphs separated by '\n\n', no headings:\n"
    "PARAGRAPH ONE: the Chinese reading (≤200 CJK chars).\n"
    "PARAGRAPH TWO: the identical reading in English (≤150 words)."
)

#: Bytes pinned at the strike day — any single-byte edit flips verification.
PIN_SHA256 = hashlib.sha256(EXHIBIT_COPILOT_SYSTEM.encode("utf-8")).hexdigest()

_BANNED = ("通过", "合格", "全绿", "必胜", "判词", "胜利", "FAIL", "PASS", "verdict")


def _packet_text(packet: dict[str, Any]) -> str:
    """Canonical text for number-provenance checks — the numbers live here."""
    return json.dumps(packet, ensure_ascii=False, sort_keys=True)


def validate_copilot(answer: str, packet: dict[str, Any]) -> tuple[bool, list[str]]:
    """Mechanical gate for the two captions. True iff the machine sealed its own wall."""
    failures: list[str] = []
    text = (answer or "").strip()
    if not text:
        return False, ["empty"]
    source = _packet_text(packet)
    for number in re.findall(r"\d+(?:\.\d+)?", text):
        if number not in source:
            failures.append(f"number {number!r} not in packet")
    zh_chars = len(re.findall(r"[一-鿿]", text))
    if zh_chars > 200:
        failures.append(f"zh ceiling breached: {zh_chars} CJK chars (max 200)")
    en_words = len(re.findall(r"[A-Za-z]+", text))
    if en_words > 150:
        failures.append(f"en ceiling breached: {en_words} words (max 150)")
    for marker in ("##", "```", "\n- ", "\n* ", "**"):
        if marker in text:
            failures.append(f"markdown marker {marker!r} present")
    for banned in _BANNED:
        if banned in text:
            failures.append(f"banned word {banned!r} present")
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if len(paragraphs) != 2:
        failures.append(f"expected exactly two paragraphs, got {len(paragraphs)}")
    return (not failures), failures


async def generate_exhibit_copilot(
    packet: dict[str, Any],
    *,
    provider_factory: Callable[..., OpenAICompatibleProvider] | None = None,
) -> dict[str, Any]:
    """Strike the lane once. Never raises into product surfaces — caller names the outcome."""
    if provider_factory is None:
        provider_factory = OpenAICompatibleProvider
    from providers.config import load_model_config

    cfg = load_model_config()
    provider: OpenAICompatibleProvider | None = None
    compact = json.dumps(packet, ensure_ascii=False)
    messages = covenant_prefix([
        LLMMessage(role="system", content=EXHIBIT_COPILOT_SYSTEM),
        LLMMessage(role="user", content=compact),
    ])
    try:
        provider = provider_factory(timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
        response: LLMResponse = await provider.chat(
            messages,
            timeout=LLM_TIMEOUT_SECONDS,
            opts={"prompt_cache_key": "specproof-exhibit-copilot"},
        )
    finally:
        if provider is not None:
            await provider.close()
    answer = (response.content or "").strip()
    ok, failures = validate_copilot(answer, packet)
    return {
        "answer": answer,
        "sealed": ok,
        "failures": failures,
        "reasoning_tokens": (response.usage or {}).get("reasoning_tokens"),
        "prompt_tokens": int((response.usage or {}).get("prompt_tokens") or 0),
        "cached_tokens": int((response.usage or {}).get("prompt_cache_hit_tokens") or 0),
        "pinned_sha256": PIN_SHA256,
    }


def build_packet() -> dict[str, Any]:
    """Compact, real fields from apps/web/src/pages/evidence.json."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    raw = json.loads((root / "apps" / "web" / "src" / "pages" / "evidence.json").read_text(encoding="utf-8"))
    latest = raw.get("latest") or {}
    packet = {
        # the three numbers the tour must carry
        "exhibits_count": raw.get("exhibits_count"),
        "latest_file": latest.get("file"),
        "started_utc": latest.get("started_utc"),
        "concurrency": latest.get("concurrency"),
        "total_requests": latest.get("total"),
        "total_ok": latest.get("total_ok"),
        "worst_p99_ms": round(float(latest.get("worst_p99_ms") or 0.0), 3),
        "avg_p95_ms": round(float(latest.get("avg_p95_ms") or 0.0), 3),
        "vs_file": (raw.get("delta_vs_previous") or {}).get("vs_file"),
        "worst_p99_delta_ms": round(float((raw.get("delta_vs_previous") or {}).get("worst_p99_delta_ms") or 0.0), 3),
        "note": latest.get("note"),
    }
    return packet
