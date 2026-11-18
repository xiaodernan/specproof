"""问世界书 —— 这一卷的读者甩不掉的问题。

This lane is public and read-only: anyone who opens the book may ask a
question about it. The book is the repo itself — the world bible
(``docs/world/SPECROOF_WORLD.md`` in zh, ``SPECROOF_WORLD_EN.md`` in en),
carrying every volume from Genesis to the present week. The model has read
it once — it rides in as the shared codex prefix, byte-frozen and cacheable
(the same sandwich the cache lanes use; the court lane never).

Discipline (mirrors ``api/observe_advice.py``):

* **the model answers from the book** — the system message pins the scope to
  the bible; out-of-scope answers are honesty failures, surfaced as such;
* **the model may never rule** — no verdicts, no approvals, no "release
  approved/denied", no exhibit colour words; it may restate the ledger and
  stay put; it may never write "已通过/未通过" about anything that ever
  happened here;
* **the question is the only client input** — printable text, capped at
  ``MAX_QUESTION_CHARS``; nothing else comes over the wire;
* **cached by fingerprint** — identical (question × locale) returns the same
  answer from Redis for the configured TTL; fail-open;
* **failure surfaces as one honest 503** — never a fabricated paragraph.
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

from api.system_codex import codex_first
from api.system_covenant import covenant_prefix
from providers.base import LLMMessage, LLMResponse
from providers.openai_compatible import OpenAICompatibleProvider

logger = logging.getLogger(__name__)

MAX_QUESTION_CHARS = 480
LLM_TIMEOUT_SECONDS = 150.0


class WorldbookAskUnavailable(Exception):
    """The model could not answer honestly right now."""


_ZH_SYSTEM = (
    "你是 SpecProof 这本铁证之书的读者。"
    "这本书叫《SPECROOF》，是一本正在被敲击的世界正史——它记录的是这个仓库里真实发生过的事。\n"
    "你只读这本书，不读别的书；你只能回答在这本书里能找到的答案。\n"
    "硬规则：\n"
    "1）同语言回答（中文问→中文答，英文问→英文答）；\n"
    "2）书里根本没写的事，直说「这本书里没写」，不许编造起源、数字、日期、人物、事件；\n"
    "3）不许做判决、不许说通过/阻断/发布批准、不许说一个展品『亮了』还是『灭了』、"
    "不许说哪个 exhibit 好还是坏——这本书没有裁决权，你作为模型也不得假装有；\n"
    "4）不用 markdown 标题，不写时间戳、人名、邮箱、URL；纯文本输出；\n"
    "5）回答可以引用书中的卷、节、提交号——书里写到什么，你就讲什么。\n"
    "只输出这一段回答，不复述规则。"
)

_EN_SYSTEM = (
    "You are a reader of the SpecProof iron-grammar bible. It records what actually "
    "happened in this repository — the volumes, the ledger, the drills, the strikes.\n"
    "Hard rules:\n"
    "1) Answer in the language you were asked;\n"
    "2) If the book does not say it, say plainly «the book does not say» — never invent a "
    "number, a person, a date, an origin, an event;\n"
    "3) Never rule. Never approve or block a release; never call any exhibit green or red; "
    "never score anything. This book has no verdict authority and neither do you;\n"
    "4) No markdown headings. No timestamps. No people, emails, URLs. Plain text only;\n"
    "5) Cite volumes, sections and commit hashes — what is in the book may be quoted; what "
    "is not, may not.\n"
    "Output only the answer itself."
)


def _sanitize_question(text: str) -> str:
    cleaned = "".join(ch for ch in (text or "") if ch.isprintable())
    cleaned = " ".join(cleaned.split())
    return cleaned[:MAX_QUESTION_CHARS]


def build_ask_messages(locale: str, question: str) -> list[LLMMessage]:
    lang = "en" if locale == "en" else "zh"
    system = _EN_SYSTEM if lang == "en" else _ZH_SYSTEM
    fence = "问题：" if lang == "zh" else "Question:"
    return codex_first(
        covenant_prefix(
            [
                LLMMessage(role="system", content=system),
                LLMMessage(role="user", content=f"{fence}{question}"),
            ]
        ),
        lang,
    )


def fingerprint(locale: str, question: str) -> str:
    return hashlib.sha256(
        f"{locale}|{_sanitize_question(question)}".encode("utf-8")
    ).hexdigest()


async def generate_ask_answer(
    question: str,
    locale: str,
    *,
    provider_factory: Callable[..., OpenAICompatibleProvider] | None = None,
) -> dict[str, Any]:
    """Ask the bible through the model. Raise WorldbookAskUnavailable on any honest failure."""
    if provider_factory is None:
        provider_factory = OpenAICompatibleProvider
    clean = _sanitize_question(question)
    if not clean:
        raise ValueError("empty question")
    started = time.perf_counter()
    provider: OpenAICompatibleProvider | None = None
    try:
        provider = provider_factory(timeout=LLM_TIMEOUT_SECONDS, max_retries=1)
        response: LLMResponse = await asyncio.wait_for(
            provider.chat(
                build_ask_messages(locale, clean),
                timeout=LLM_TIMEOUT_SECONDS,
                opts={"prompt_cache_key": "specproof-worldbook-ask"},
            ),
            timeout=LLM_TIMEOUT_SECONDS + 5,
        )
    except Exception as exc:  # noqa: BLE001 - provider failure becomes one honest error
        logger.info("worldbook-ask provider failure: %s", type(exc).__name__)
        raise WorldbookAskUnavailable(
            "the model is unavailable right now — the book is intact; try again later or read it yourself."
            if locale == "en"
            else "模型暂时不可用——书还在；稍后再试，或者自己翻。"
        ) from exc
    finally:
        if provider is not None:
            with contextlib.suppress(Exception):
                await provider.close()
    text = (response.content or "").strip()
    if not text:
        raise WorldbookAskUnavailable(
            "the model returned an empty answer — nothing is shown rather than something "
            "misleading; read the book."
            if locale == "en"
            else "模型返回了空答复——为避免误导，这里不展示任何内容；自己翻书。"
        )
    usage = response.usage if response.usage is not None else {}
    return {
        "answer": text,
        "model": response.model or None,
        "model_latency_ms": round((time.perf_counter() - started) * 1000),
        "usage": usage,
        "question_chars": len(clean),
    }


_redis_singleton: Any | None = None


def ask_redis() -> Any | None:
    """Lazy Redis handle for the ask-the-book lane (fail-open)."""
    global _redis_singleton
    if _redis_singleton is None:
        try:
            from storage.redis import RedisStore

            _redis_singleton = RedisStore()
        except Exception:  # noqa: BLE001 - cache is an accelerator, never a dependency
            return None
    return _redis_singleton
