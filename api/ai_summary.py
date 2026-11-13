"""AI 解读：把一份持久化的验收摘要编译成评审者能直接读的中文解读。

设计边界（与网关现有能力一致，同一纪律）：

* **证据包只发给模型，不给用户泄漏别处**——数据只含本次验收已经展示给
  评审者的事实（结论、契约行、finding 计数），不含路径、凭证或业务数据；
* **有缓存**——同一份证据只生成一次；job 的矩阵或 finding 计数一变，缓存失效
  （fingerprint 变化），才再次消耗 token；
* **绝不捏造**——证据不支持的结论让模型说"本次证据不足"，不许它替系统下结论；
* **模型输出是解读，不是判决**——UI 标注为 AI 解读，判决仍来自确定性证据路径；
  失败时如实报错，绝不补一段假总结。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from providers.base import LLMMessage, LLMResponse
from providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

#: Packet budget — anything longer stops being "reviewer's 90-second read".
MAX_PACKET_CHARS = 6_000
MAX_ROWS = 10
MAX_FINDINGS = 8
#: LLM call budget — a summary that takes longer than this is not a summary.
LLM_TIMEOUT_SECONDS = 45.0


class AiSummaryUnavailable(Exception):
    """The model could not produce an honest summary right now."""


def _matrix_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows = summary.get("matrix_rows")
    if isinstance(rows, list):
        return [r for r in rows if isinstance(r, dict)]
    return []


def _count_by(summary: dict[str, Any], key: str) -> int:
    value = summary.get(key)
    return int(value) if isinstance(value, (int, float)) else 0


def build_evidence_packet(summary: dict[str, Any], *, findings: list[dict[str, Any]] | None = None) -> str:
    """Serialize the smallest evidence packet that supports an honest read."""
    rows = _matrix_rows(summary)
    blocked = [
        {
            "id": row.get("contract_id"),
            "result": row.get("result"),
            "severity": row.get("severity"),
            "evidence": row.get("evidence_type"),
        }
        for row in rows
        if str(row.get("result") or "").upper() == "FAIL"
    ][:MAX_ROWS]
    unverified = [
        {"id": row.get("contract_id"), "unverified_reason": row.get("unverified_reason")}
        for row in rows
        if str(row.get("result") or "").upper() == "UNVERIFIED"
    ][:MAX_ROWS]
    capsules = summary.get("capsules")
    packet = {
        "verdict": summary.get("verdict"),
        "contracts_total": summary.get("contracts_total") or (len(rows) or None),
        "matrix_passed": _count_by(summary, "matrix_passed"),
        "matrix_failed": _count_by(summary, "matrix_failed"),
        "matrix_unverified": _count_by(summary, "matrix_unverified"),
        "blocked_contracts": blocked,
        "unverified_contracts": unverified,
        "finding_total": (findings and len(findings)) or summary.get("findings_total"),
        "capsules": len(capsules) if isinstance(capsules, list) else None,
        "coverage_reason": summary.get("coverage_reason"),
        "errors": [str(e) for e in (summary.get("errors") or [])][:5],
        "retrieval_note": summary.get("retrieval_note"),
    }
    text = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    if len(text) > MAX_PACKET_CHARS:
        # Shrink the two unbounded lists first — the counts above stay true.
        packet["blocked_contracts"] = blocked[: max(3, len(blocked) // 4)]
        packet["unverified_contracts"] = unverified[:3]
        packet["truncated"] = True
        text = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    return text


def fingerprint(summary: dict[str, Any], findings: list[dict[str, Any]] | None = None) -> str:
    """Stable digest of the evidence that determines the summary's content."""
    rows = _matrix_rows(summary)
    material = {
        "verdict": summary.get("verdict"),
        "passed": _count_by(summary, "matrix_passed"),
        "failed": _count_by(summary, "matrix_failed"),
        "unverified": _count_by(summary, "matrix_unverified"),
        "rows": sorted(
            (
                str(row.get("contract_id") or ""),
                str(row.get("result") or ""),
                str(row.get("severity") or ""),
            )
            for row in rows
        ),
        "finding_total": (findings and len(findings)) or summary.get("findings_total"),
        "coverage_reason": summary.get("coverage_reason"),
    }
    return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


_PROMPT = (
    "你是 SpecProof 的验收解读助手。请用中文为评审者写一段解读，要求：\n"
    "1. 第一句必须是这个结论的一句话定性（通过/受阻/存疑，必须与 verdict 一致），不许加戏；\n"
    "2. 接着用 2-3 句话说清楚「哪些契约被阻止了、为什么（证据类型）」，没有阻止项就说没有；\n"
    "3. 再给出评审者下一步应该做的 1-3 件具体事；\n"
    "4. 不编造任何事实——证据里没有的数字、ID、路径、原因都不许写；\n"
    "5. 不要 Markdown 标题、不要列表符号以外的格式，纯文本，总长不超过 400 字。\n"
    "只输出解读文本，不要别的内容。"
)


def _prompt(packet: str) -> list[LLMMessage]:
    return [
        LLMMessage(role="system", content=_PROMPT),
        LLMMessage(role="user", content="证据包（JSON）：\n" + packet),
    ]


async def generate_ai_summary(
    summary: dict[str, Any],
    findings: list[dict[str, Any]] | None = None,
    *,
    provider_factory: Callable[..., OpenAICompatibleProvider] | None = None,
) -> dict[str, Any]:
    """Call the model; raise AiSummaryUnavailable on any honest failure."""
    if provider_factory is None:
        provider_factory = OpenAICompatibleProvider
    packet = build_evidence_packet(summary, findings=findings)
    provider: OpenAICompatibleProvider | None = None
    started = time.perf_counter()
    try:
        provider = provider_factory(timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
        response: LLMResponse = await asyncio.wait_for(
            provider.chat(_prompt(packet), timeout=LLM_TIMEOUT_SECONDS),
            timeout=LLM_TIMEOUT_SECONDS + 5,
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure becomes one honest error
        logger.info("ai-summary provider failure: %s", type(exc).__name__)
        raise AiSummaryUnavailable(
            "模型暂时不可用，无法生成 AI 解读。可以稍后重试，或直接阅读上方证据。"
        ) from exc
    finally:
        if provider is not None:
            try:
                await provider.close()
            except Exception:  # noqa: BLE001 - close is best-effort
                pass
    text = (response.content or "").strip()
    if not text:
        raise AiSummaryUnavailable(
            "模型返回了空解读。为避免误导，这里不显示任何内容；请直接阅读上方证据。"
        )
    return {
        "summary": text,
        "model_latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": response.usage,
        "evidence_packet_chars": len(packet),
    }


async def generate_ai_summary_stream(
    summary: dict[str, Any],
    findings: list[dict[str, Any]] | None = None,
    *,
    provider_factory: Callable[..., OpenAICompatibleProvider] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Streaming twin of generate_ai_summary.

    Yields SSE-ready event dicts:

      {"type": "delta", "text": piece}   — one per non-empty content chunk
                                           (the client accumulates);
      {"type": "done",  "summary": full, "model_latency_ms": ...,
       "usage": ..., "evidence_packet_chars": ...}

    Any provider failure mid-stream (or an empty final text) yields
    {"type": "error", "detail": ..., "partial": text-so-far} instead of
    raising — the client keeps whatever already arrived and shows the honest
    error; nothing is fabricated to fill the gap.
    """
    if provider_factory is None:
        provider_factory = OpenAICompatibleProvider
    packet = build_evidence_packet(summary, findings=findings)
    provider: OpenAICompatibleProvider | None = None
    started = time.perf_counter()
    pieces: list[str] = []
    last_usage: dict[str, Any] | None = None
    try:
        provider = provider_factory(timeout=LLM_TIMEOUT_SECONDS, max_retries=0)
        stream = provider.chat_stream(
            _prompt(packet), timeout=LLM_TIMEOUT_SECONDS,
        )
        async for response in stream:
            usage = response.usage
            if isinstance(usage, dict) and usage:
                last_usage = usage
            piece = response.content or ""
            if piece:
                pieces.append(piece)
                yield {"type": "delta", "text": piece}
        text = "".join(pieces).strip()
        if not text:
            raise AiSummaryUnavailable(
                "模型返回了空解读。为避免误导，这里不显示任何内容；请直接阅读上方证据。"
            )
        yield {
            "type": "done",
            "summary": text,
            "model_latency_ms": round((time.perf_counter() - started) * 1000),
            "usage": last_usage,
            "evidence_packet_chars": len(packet),
        }
    except AiSummaryUnavailable as exc:
        yield {"type": "error", "detail": str(exc), "partial": "".join(pieces)}
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - any provider failure is one honest error
        logger.info("ai-summary stream provider failure: %s", type(exc).__name__)
        yield {
            "type": "error",
            "detail": "模型暂时不可用，无法生成 AI 解读。可以稍后重试，或直接阅读上方证据。",
            "partial": "".join(pieces),
        }
    finally:
        if provider is not None:
            try:
                await provider.close()
            except Exception:  # noqa: BLE001 - close is best-effort
                pass
