"""Next-step advice — the model reads this repository's real numbers and says
what this shipped world probably wants to strike next.

The packet is derived from the repo tree itself (never an invented figure):
ledger/chronicle/worldbook/library counts, git identity, and unit-test file
count. Everything is computed at call time from the working tree, so this
lane cannot drift from the ledger.

Discipline — identical in shape to ``api/observe_advice.py``:

* public lane, anonymous, cacheable by fingerprint (packet bytes are
  deterministic);
* the model may NEVER rule; it may quote packet numbers and read the book,
  and that is the whole job;
* the codex rides along (``codex_first`` — the same byte-frozen world book),
  so the model answering "what next" is the model who has read the bible;
* on any honest failure: one 503-style exception, never a fabricated
  paragraph and never a verdict;
* the court is never here; nothing about exhibits is green or red.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

from api.system_codex import bilingual_packet_messages
from providers.base import LLMResponse
from providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 150.0

_ROOT = Path(__file__).resolve().parents[1]


class NextStepAdviceError(Exception):
    """The model could not answer honestly right now."""


def _read_json(path: str) -> Any:
    return json.loads((_ROOT / path).read_text(encoding="utf-8"))


def build_next_step_packet() -> dict[str, Any]:
    repo = _read_json("apps/web/src/pages/repoStats.json")
    worldbook = _read_json("apps/web/src/pages/worldbook.json")
    library = _read_json("apps/web/src/pages/library.json")
    chronicle = _read_json("apps/web/src/pages/chronicle.json")
    unit_tests = sorted((_ROOT / "tests" / "unit").glob("test_*.py"))
    return {
        "commits": repo.get("git_commit_count"),
        "ledger_sections": repo.get("ledger_sections"),
        "repository_files": repo.get("repository_files"),
        "lines_of_code": repo.get("total_lines_of_source"),
        "worldbooks_volumes": len(worldbook.get("locales", {}).get("zh", {}).get("volumes", [])),
        "library_zh_en_pairs": library.get("count"),
        "chronicle_entries": len(chronicle) if isinstance(chronicle, list) else None,
        "unit_test_files": len(unit_tests),
        "court_lock": "4117d2b0ca5fb23a",
    }


def fingerprint(locale: str) -> str:
    return hashlib.sha256(
        json.dumps({"packet": build_next_step_packet(), "locale": "en" if locale == "en" else "zh"},
                   ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


_PROMPT_ZH = (
    "你是 SpecProof 世界目前的下一步判断者——但你没有裁决权，你只是一个读过整本书的读者。\n"
    "下面这份 JSON 是本仓的真数字（确定性、逐字引用即可）：ledger / chronicle / worldbook / library / unit tests。\n"
    "请直接写一段中文，不超过 240 字，规则：\n"
    "1）先说包里的数字——commits、chronicle、worldbook_volumes、library_zh_en_pairs 至少引用 3 个；\n"
    "2）然后回答「这本书接下来最值得落一笔的东西是什么」——只许引用包内数字或书里写过的事实，\n"
    "   不许编造新数字、新人、新日期、新展品编号；证据不够就直说「本包无法判断 X」；\n"
    "3）不许做任何判决——不使用「通过／未通过／批准／阻止／验收结论」等词；\n"
    "4）纯文本输出，不用 Markdown 标题；不写时间戳、人名、邮箱、URL；\n"
    "5）第一句说这本书当前的形状，最后一句说一个可落纸的下一步（一句话）。\n"
    "只输出这段回答，不复述规则。"
)

_PROMPT_EN = (
    "You are the read-along reader of the SpecProof world right now — with no verdict authority.\n"
    "The JSON below is this repository's real numbers (deterministic — quote exactly): "
    "ledger / chronicle / worldbook / library / unit tests.\n"
    "Write one English paragraph, at most 140 words, hard rules:\n"
    "1) Open with the packet's shape — quote at least 3 of commits, chronicle_entries, "
    "worldbooks_volumes, library_zh_en_pairs verbatim;\n"
    "2) Answer the one question: what is this book's next most worthwhile strike — "
    "quote ONLY packet numbers or facts the world book has already recorded; "
    "if evidence is thin, say “this packet cannot support X”;\n"
    "3) Never rule — no approved/blocked/accepted/denied/verdict vocabulary anywhere;\n"
    "4) Plain text only — no Markdown headings, no timestamps, no people, no emails, no URLs;\n"
    "5) First sentence states the shape; last sentence names one concrete next step.\n"
    "Output only the answer itself."
)


_prompt = partial(
    bilingual_packet_messages, system_zh=_PROMPT_ZH, system_en=_PROMPT_EN
)  # one prompt builder; each lane supplies only its two system strings

async def generate_next_step_advice(
    locale: str,
    *,
    provider_factory: Callable[..., OpenAICompatibleProvider] | None = None,
) -> dict[str, Any]:
    """Call the model; raise NextStepAdviceError on any honest failure."""
    if provider_factory is None:
        provider_factory = OpenAICompatibleProvider
    packet = json.dumps(build_next_step_packet(), ensure_ascii=False, sort_keys=True)
    provider: OpenAICompatibleProvider | None = None
    started = time.perf_counter()
    try:
        provider = provider_factory(timeout=LLM_TIMEOUT_SECONDS, max_retries=1)
        response: LLMResponse = await asyncio.wait_for(
            provider.chat(
                _prompt(locale, packet),
                timeout=LLM_TIMEOUT_SECONDS,
                opts={"prompt_cache_key": "specproof-next-step-advice"},
            ),
            timeout=LLM_TIMEOUT_SECONDS + 5,
        )
    except Exception as exc:  # noqa: BLE001 - any provider failure becomes one honest error
        logger.info("next-step-advice provider failure: %s", type(exc).__name__)
        raise NextStepAdviceError(
            "模型暂时不可用，无法生成下一步读法。稍后再试，或直接读账吧。"
            if locale != "en"
            else "The model is unavailable right now; no next-step reading. "
            "Read the numbers yourself — they are not hiding."
        ) from exc
    finally:
        if provider is not None:
            with contextlib.suppress(Exception):
                await provider.close()
    text = (response.content or "").strip()
    if not text:
        raise NextStepAdviceError(
            "模型返回了空解读。为避免误导，这里不显示任何内容。"
            if locale != "en"
            else "The model returned an empty reading. Nothing is shown rather than mislead."
        )
    return {
        "advice": text,
        "model": response.model or None,
        "model_latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": response.usage,
        "evidence_packet_chars": len(packet),
    }


_redis_singleton: Any | None = None


def next_step_redis() -> Any | None:
    """Lazy Redis handle for the next-step lane (fail-open)."""
    global _redis_singleton
    if _redis_singleton is None:
        try:
            from storage.redis import RedisStore

            _redis_singleton = RedisStore()
        except Exception:  # noqa: BLE001 - cache accelerates; never a dependency
            return None
    return _redis_singleton
