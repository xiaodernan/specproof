"""Observatory AI read — the model reads the public calibration panel, honestly.

The ``/observe`` page is public, read-only and demo-only: everyone in the
world can open it. The numbers on it are a seeded, deterministic 240-member
SYNTHETIC calibration cohort (see ``api/synthetic_cohort.py``) plus this
browser's own localStorage taps. No real person appears anywhere in the
packet; there is nobody to surveil.

Discipline (mirrors ``api/insight_advice.py`` and ``api/ai_summary.py``):

* **server computes the packet — clients never submit numbers** — the only
  input is the language (``locale``); the packet is the exact aggregate the
  panel renders, and it is identical for every visitor;
* **the model may not invent** — the prompt forbids any number/ID/trend not
  present in the packet; thin evidence is to be called out, not papered over;
* **never a verdict** — this lane can never output CONFIRMED/BLOCKED/
  REJECTED-shaped verdicts and cannot reach the court lane;
* **cached by fingerprint** — identical cohort ⇒ identical answer (Redis,
  TTL like the insight-advice lane; fail-open). Not court; cached rides are
  allowed here;
* **failure surfaces as one honest 503** — never a fabricated paragraph.

The module owns the protocol objects; the public route lives in
``api/routes/observe.py`` mounted outside the RBAC-governed ``/api`` prefix
and opened in the tenant-mode middleware alongside ``/health``.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from api.synthetic_cohort import cohort
from api.system_covenant import covenant_prefix
from api.system_codex import codex_first
from providers.base import LLMMessage, LLMResponse
from providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

#: The packet is ~700 bytes; it should not grow into a "document analysis".
MAX_PACKET_CHARS = 2_000
LLM_TIMEOUT_SECONDS = 150.0  # codex era: byte-identical ~100K-token prefix; 45s predates the bible


class ObserveAdviceUnavailable(Exception):
    """The model could not produce an honest reading right now."""


def build_observe_packet(locale: str) -> str:
    """Serialize the cohort aggregates into the bounded, fingerprint-stable packet."""
    c = cohort()
    lang = "zh" if locale != "en" else "en"
    packet: dict[str, Any] = {
        "locale": lang,
        "synthetic": True,
        "seed": c["seed"],
        "population": c["population"],
        "sessions_today": c["sessions_today"],
        "sessions_per_day": c["sessions_per_day"],
        "predicted_next_7": c["predicted_next_7"],
        "daily_slope_per_day": round(c["daily_slope_per_day"], 4),
        "r2": round(c["r2"], 4),
        "tour_completion_rate": round(c["tour_completion_rate"], 4),
        "drill_pass_rate": c["drill_pass_rate"],
        "median_dwell_min": c["median_dwell_min"],
        "funnel": [{"k": s["key"], "n": s["count"]} for s in c["funnel"]],
        "personas": [{"k": p["key"], "n": p["count"]} for p in c["personas"]],
        "features": [{"k": f["key"], "n": f["users"]} for f in c["features"]],
    }
    text = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= MAX_PACKET_CHARS:
        return text
    # deterministic shrink rule: lists keep their tails, head intact ordering
    packet["sessions_per_day"] = packet["sessions_per_day"][-14:]
    packet["truncated"] = True
    return json.dumps(packet, ensure_ascii=False, separators=(",", ":"))


def fingerprint(locale: str) -> str:
    """Stable digest of the packet + locale — cache key material."""
    return hashlib.sha256(build_observe_packet(locale).encode()).hexdigest()


_PROMPT_ZH = (
    "你是 SpecProof 观察舱的分析师。下面这份 JSON 是一块「公开·只读·演示」面板上"
    "显示的全部数字：一个 240 人的合成校准群体（mulberry32 种子 20261115，确定性构造），"
    "没有任何真实用户，也没有其他浏览器的数据。\n"
    "请用中文写一段不超过 280 字的解读，硬规则：\n"
    "① 第一句定性这条轨迹的形状——按包里的 slope 与 r2 如实说出"
    "『近乎平、略下滑、拟合弱（r²≈0.12）』之类的话，不允许把这条轨迹说成增长或衰退的故事；\n"
    "② 原样引用包内数字"
    "（population、slope、r2、sessions_today、predicted_next_7、funnel、drill_pass_rate、"
    "tour_completion_rate、median_dwell_min）；\n"
    "③ 明确说出这是合成校准数据，不代表任何真实人或真实产品健康度，"
    "本段不是判决、不是对任何人的建议；\n"
    "④ 包里没出现的数字一律不许写；证据不够就直说『本包数据不足以判断 X』；\n"
    "⑤ 纯文本输出，不用 Markdown 标题；不写时间戳、人名、邮箱、URL。\n"
    "只输出这段解读文本。"
)

_PROMPT_EN = (
    "You are the analyst for SpecProof's public Observatory — a PUBLIC, READ-ONLY, DEMO panel. "
    "The JSON below is everything shown on that page: a seeded 240-member synthetic calibration "
    "cohort (mulberry32 seed 20261115, deterministic). There is no real person in it; no other "
    "visitor's data exists here.\n"
    "Write a reading of at most 170 words, hard rules:\n"
    "1. Open with the shape of the trajectory as the packet's slope and r2"
    " actually read — flat, mildly cooling, and a weak fit (r²≈0.12)."
    " Do not narrate this as a growth or a decline story;\n"
    "2. Quote in-packet numbers verbatim (population, slope, r2, sessions_today, predicted_next_7, "
    "funnel, drill_pass_rate, tour_completion_rate, median_dwell_min);\n"
    "3. State plainly this is synthetic calibration data — not anyone's real behaviour, not the "
    "product's health, not a verdict, and advice to no one;\n"
    "4. Nothing beyond the packet may be written; where evidence is thin, say "
    "\"this packet cannot support X\";\n"
    "5. Plain text, no Markdown headings, no timestamps, no names, no emails, no URLs.\n"
    "Output only the reading."
)


def _prompt(locale: str, packet: str) -> list[LLMMessage]:
    lang = "zh" if locale != "en" else "en"
    system = _PROMPT_ZH if lang == "zh" else _PROMPT_EN
    return codex_first(covenant_prefix([
        LLMMessage(role="system", content=system),
        LLMMessage(
            role="user",
            content=("数据包（JSON）：\n" if lang == "zh" else "Packet (JSON):\n") + packet,
        ),
    ]), lang)


async def generate_observe_advice(
    locale: str,
    *,
    provider_factory: Callable[..., OpenAICompatibleProvider] | None = None,
) -> dict[str, Any]:
    """Call the model; raise ObserveAdviceUnavailable on any honest failure."""
    if provider_factory is None:
        provider_factory = OpenAICompatibleProvider
    packet = build_observe_packet(locale)
    provider: OpenAICompatibleProvider | None = None
    started = time.perf_counter()
    try:
        # One retry covers the observed instant-refusal window on this host
        # (mihomo refuses CONNECT at peak). A retry doubles the worst case to
        # ~90s but the 45s per-attempt budget and the 50s wait_for still
        # bound it, and a success is never billed twice — the retry only
        # opens after a connect-level failure with zero tokens spent.
        provider = provider_factory(timeout=LLM_TIMEOUT_SECONDS, max_retries=1)
        response: LLMResponse = await asyncio.wait_for(
            provider.chat(
                _prompt(locale, packet),
                timeout=LLM_TIMEOUT_SECONDS,
                opts={"prompt_cache_key": "specproof-observe-advice"},
            ),
            timeout=LLM_TIMEOUT_SECONDS + 5,
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure becomes one honest error
        logger.info("observe-advice provider failure: %s", type(exc).__name__)
        raise ObserveAdviceUnavailable(
            "模型暂时不可用，无法生成观察舱解读。稍后再试，或直接阅读本页数字面板。"
            if locale != "en"
            else "The model is unavailable right now; the Observatory read cannot be generated. "
            "Try again later, or just read the numbers on this page."
        ) from exc
    finally:
        if provider is not None:
            with contextlib.suppress(Exception):  # close is best-effort
                await provider.close()
    text = (response.content or "").strip()
    if not text:
        raise ObserveAdviceUnavailable(
            "模型返回了空解读。为避免误导，这里不显示任何内容；请直接阅读本页的数字面板。"
            if locale != "en"
            else ("The model returned an empty reading. Nothing is shown rather than "
                  "something misleading — read the numbers on this page.")
        )
    return {
        "advice": text,
        "model": response.model or None,
        "model_latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": response.usage,
        "evidence_packet_chars": len(packet),
    }


_redis_singleton: Any | None = None


def observe_redis() -> Any | None:
    """Lazy Redis handle for the Observatory lane (fail-open: the cache
    accelerates the common case, it is never a dependency)."""
    global _redis_singleton
    if _redis_singleton is None:
        try:
            from storage.redis import RedisStore

            _redis_singleton = RedisStore()
        except Exception:  # noqa: BLE001 - cache is an accelerator, not a dependency
            return None
    return _redis_singleton
