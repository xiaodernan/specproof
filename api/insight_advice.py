"""Insight AI 解读 — the model reads the Insight Deck, honestly.

Same discipline as ``api/ai_summary.py`` (the AI-interpretation lane on the
acceptance page):

* **only what the panel already shows leaves the process** — a bounded,
  allowlisted packet of the very aggregate numbers rendered on the Insight
  Deck (synthetic calibration population + this browser's real tap climate).
  No user ids, no emails, no raw session payloads, no paths beyond the
  browser's own local beats;
* **the model may not invent** — the prompt forbids any number/ID/trend not
  present in the packet; if the evidence is thin the model is told to say so
  rather than fill the gap;
* **AI 解读 is never a verdict** — the UI labels it as such; RBAC stays
  fail-closed; failure surfaces as one honest error, never as a fabricated
  paragraph of advice;
* **cached by fingerprint** — identical packet ⇒ identical answer (Redis,
  TTL shared with the ai-summary lane; fail-open). Not court, not the judge
  lane: cached ride is allowed here.

This module owns the protocol objects; the route lives in
``api/routes/admin.py`` (admin/operator, tenant-mode like every admin law).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from providers.base import LLMMessage, LLMResponse
from providers.openai_compatible import OpenAICompatibleProvider

from api.system_covenant import covenant_prefix

logger = logging.getLogger(__name__)

#: Packet budget — longer than this stops being "a 90-second admin read".
MAX_PACKET_CHARS = 4_000
#: Same spirit as the ai-summary lane: advice should not take a coffee.
LLM_TIMEOUT_SECONDS = 45.0

#: Allowlist of scalar keys the panel may send. Anything else is dropped —
#: deliberately, not by accident — so a future frontend hack cannot grow the
#: packet's surface from the outside.
_SCALAR_KEYS = frozenset(
    {
        "population",
        "slope_per_day",
        "r2",
        "sessions_today",
        "median_dwell_min",
        "drill_pass_rate",
        "tour_completion_rate",
        "heat_taps_total",
        "heat_rage_count",
        "onboarding_routes",
    }
)
#: Allowlisted list keys, each entry a {"k": str, "v": int|float}.
_LIST_KEYS = frozenset({"funnel", "features", "personas"})
_LIST_MAX = 8
_ENTRY_KEY_MAX = 60


class InsightAdviceUnavailable(Exception):
    """The model could not produce an honest reading right now."""


def _coerce_number(value: Any) -> int | float | None:
    if isinstance(value, bool):  # bools are ints in disguise; refuse them
        return None
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return None
        if value in (float("inf"), float("-inf")):
            return None
        return value
    return None


def _sanitize_list(value: Any, limit: int = _LIST_MAX) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in value[:limit]:
        if not isinstance(entry, dict):
            continue
        key = entry.get("k")
        number = _coerce_number(entry.get("v"))
        if not isinstance(key, str) or number is None:
            continue
        out.append({"k": key.strip()[:_ENTRY_KEY_MAX], "v": number})
    return out


def sanitize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    """Return the bounded, allowlisted packet object (never raises on junk —
    junk just doesn't survive the allowlist)."""
    if not isinstance(stats, dict):
        return {}
    safe: dict[str, Any] = {}
    for key in _SCALAR_KEYS:
        if key in stats:
            number = _coerce_number(stats[key])
            if number is not None:
                safe[key] = number
    for key in _LIST_KEYS:
        if key in stats:
            safe[key] = _sanitize_list(stats[key])
    return safe


def build_insight_packet(stats: dict[str, Any]) -> str:
    """Serialize the sanitized packet; shrink lists before truncating counts."""
    safe = sanitize_stats(stats)
    text = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= MAX_PACKET_CHARS:
        return text
    for key in list(safe):
        if key in _LIST_KEYS:
            safe[key] = safe[key][:3]
    safe["truncated"] = True
    return json.dumps(safe, ensure_ascii=False, separators=(",", ":"))


def fingerprint(stats: dict[str, Any]) -> str:
    """Stable digest of the packet — cache key material."""
    safe = sanitize_stats(stats)
    return hashlib.sha256(
        json.dumps(safe, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


_PROMPT = (
    "你是 SpecProof 洞察舱的数据解读助手。下面这份 JSON 是「洞察舱」这块面板上"
    "公开可见的匿名聚合遥测，由确定性合成校准样本与本浏览器此刻真实的行为统计构成。\n"
    "请用中文写一段不超过 400 字的解读，要求：\n"
    "1. 第一句先定性最值得注意的现象（总体繁忙 / 某环节掉人 / 某功能采用率高低 / 预测方向），数字必须原样引用自包；\n"
    "2. 指出 1-2 个最值得跟的瓶颈，必须引到包内的数字（例如漏斗某段转化率、热区、预测斜率、留存率）；\n"
    "3. 给出 1-3 件可以立刻做的优化动作，动作要具体到页面 / 流程 / 文案 / 门控方向；\n"
    "4. 包里没有的数字、ID、路径、人物一律不许写；证据不够就直说『本包数据不足以判断 X』；\n"
    "5. 不用 Markdown 标题，列表最多用「①②、-」；纯文本，总长不超过 400 字。\n"
    "只输出解读文本。"
)


def _prompt(packet: str) -> list[LLMMessage]:
    return covenant_prefix([
        LLMMessage(role="system", content=_PROMPT),
        LLMMessage(role="user", content="数据包（JSON）：\n" + packet),
    ])


async def generate_insight_advice(
    stats: dict[str, Any],
    *,
    provider_factory: Callable[..., OpenAICompatibleProvider] | None = None,
) -> dict[str, Any]:
    """Call the model; raise InsightAdviceUnavailable on any honest failure."""
    if provider_factory is None:
        provider_factory = OpenAICompatibleProvider
    packet = build_insight_packet(stats)
    provider: OpenAICompatibleProvider | None = None
    started = time.perf_counter()
    try:
        provider = provider_factory(timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
        response: LLMResponse = await asyncio.wait_for(
            provider.chat(_prompt(packet), timeout=LLM_TIMEOUT_SECONDS),
            timeout=LLM_TIMEOUT_SECONDS + 5,
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure becomes one honest error
        logger.info("insight-advice provider failure: %s", type(exc).__name__)
        raise InsightAdviceUnavailable(
            "模型暂时不可用，无法生成 AI 解读。可以稍后重试，或直接阅读本页的数字面板。"
        ) from exc
    finally:
        if provider is not None:
            try:
                await provider.close()
            except Exception:  # noqa: BLE001 - close is best-effort
                pass
    text = (response.content or "").strip()
    if not text:
        raise InsightAdviceUnavailable(
            "模型返回了空解读。为避免误导，这里不显示任何内容；请直接阅读本页的数字面板。"
        )
    return {
        "advice": text,
        "model": response.model or None,
        "model_latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": response.usage,
        "evidence_packet_chars": len(packet),
    }


_redis_singleton: Any | None = None


def insight_redis() -> Any | None:
    """Lazy Redis handle for the advice lane (fail-open: cache is optional,
    never a dependency)."""
    global _redis_singleton
    if _redis_singleton is None:
        try:
            from storage.redis import RedisStore

            _redis_singleton = RedisStore()
        except Exception:  # noqa: BLE001 - cache is an accelerator, not a dependency
            return None
    return _redis_singleton
